"""LangChain ``BaseChatModel`` wrapper around the Code Assist endpoint.

Used by ``agents.model_router.build_llm`` when the chosen provider is
``gemini-cli`` (OAuth-backed). We translate LangChain messages + tools
to the Gemini ``generateContent`` schema, wrap them in the Code Assist
envelope, and POST with the OAuth bearer token.

Tool calls round-trip:

* outbound: each LangChain ``Tool`` (or pydantic-schema dict) becomes a
  ``functionDeclaration`` in the request.
* inbound: ``functionCall`` parts on Gemini's reply become
  ``AIMessage.tool_calls`` entries the rest of the reactive subgraph
  already knows how to handle.
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Iterator, Sequence

import httpx
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.tools import BaseTool
from pydantic import Field

from agents.gemini_oauth import (
    CODE_ASSIST_ENDPOINT,
    CODE_ASSIST_USER_AGENT,
    get_valid_access_token,
    onboard_project,
)

logger = logging.getLogger(__name__)


def _safe_tool_name(name: str) -> str:
    out = "".join(c if c.isalnum() or c == "_" else "_" for c in name or "")
    return out[:64] or "tool"


def _retry_wait_seconds(r: "httpx.Response", budget: int) -> float | None:
    """Decide how long to wait before retrying a 429.

    Priority order:

    1. ``Retry-After`` header (whole seconds, RFC 7231).
    2. Google's structured ``"reset after Xs"`` hint inside the JSON body.
    3. A flat 5-second fallback.

    Returns ``None`` if we shouldn't retry (budget exhausted or no sensible
    hint to wait for).
    """
    if budget <= 0:
        return None

    retry_after = r.headers.get("Retry-After", "").strip()
    if retry_after.isdigit():
        wait = float(retry_after)
        return min(wait, float(budget))

    # Read the streamed body so we can inspect the error envelope.
    try:
        r.read()
    except Exception:  # noqa: BLE001
        pass
    body_text = ""
    try:
        body_text = r.text or ""
    except Exception:  # noqa: BLE001
        return min(5.0, float(budget))

    # Google's hint looks like: "Your quota will reset after 51s."
    import re as _re

    m = _re.search(r"reset after\s+(\d+)\s*s", body_text)
    if m:
        wait = float(m.group(1)) + 1.0  # small jitter past the boundary
        return min(wait, float(budget))
    return min(5.0, float(budget))


def _messages_to_gemini(
    messages: Sequence[BaseMessage],
) -> tuple[list[dict[str, Any]], str | None]:
    """Translate LangChain messages -> Gemini ``contents`` array + system instruction."""
    contents: list[dict[str, Any]] = []
    system_text: list[str] = []
    for m in messages:
        if isinstance(m, SystemMessage):
            system_text.append(_message_text(m))
            continue
        if isinstance(m, HumanMessage):
            contents.append({"role": "user", "parts": [{"text": _message_text(m)}]})
            continue
        if isinstance(m, ToolMessage):
            contents.append({
                "role": "user",
                "parts": [{
                    "functionResponse": {
                        "name": _safe_tool_name(getattr(m, "name", "") or ""),
                        "response": {"content": _message_text(m)},
                    }
                }],
            })
            continue
        if isinstance(m, AIMessage):
            parts: list[dict[str, Any]] = []
            text = _message_text(m)
            if text:
                parts.append({"text": text})
            for call in getattr(m, "tool_calls", None) or []:
                parts.append({
                    "functionCall": {
                        "name": _safe_tool_name(call.get("name", "")),
                        "args": call.get("args") or {},
                    }
                })
            if parts:
                contents.append({"role": "model", "parts": parts})
            continue
        # Anything else, treat as plain user input.
        contents.append({"role": "user", "parts": [{"text": _message_text(m)}]})
    return contents, "\n\n".join(system_text) if system_text else None


def _message_text(m: BaseMessage | Any) -> str:
    content = getattr(m, "content", m)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out = []
        for part in content:
            if isinstance(part, str):
                out.append(part)
            elif isinstance(part, dict):
                text = part.get("text") or part.get("content")
                if isinstance(text, str):
                    out.append(text)
        return "".join(out)
    return str(content or "")


def _tools_to_function_declarations(tools: Sequence[Any]) -> list[dict[str, Any]]:
    decls: list[dict[str, Any]] = []
    for t in tools or []:
        if isinstance(t, BaseTool):
            schema = t.args_schema
            params: dict[str, Any] = {"type": "object", "properties": {}}
            if schema is not None:
                try:
                    params = schema.model_json_schema()  # pydantic v2
                except AttributeError:
                    try:
                        params = schema.schema()  # pydantic v1
                    except Exception:
                        params = {"type": "object", "properties": {}}
            decls.append({
                "name": _safe_tool_name(t.name),
                "description": (t.description or "")[:1024],
                "parameters": _normalize_schema(params),
            })
            continue
        if isinstance(t, dict) and t.get("name"):
            decls.append({
                "name": _safe_tool_name(t["name"]),
                "description": (t.get("description") or "")[:1024],
                "parameters": _normalize_schema(t.get("parameters") or {}),
            })
    return decls


_STRIP_META_KEYS = {"title", "$ref", "$defs", "definitions"}


def _normalize_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Strip pydantic-isms Gemini's API doesn't like ($ref, title, allOf).

    Property *names* are user-chosen and never filtered — only schema
    *metadata* keys are stripped. Conflating the two used to delete fields
    literally named ``title`` (Calendar event title, doc title, …) while
    leaving them in ``required``, producing a 400 from Code Assist.
    """
    if not isinstance(schema, dict):
        return {"type": "object", "properties": {}}
    out: dict[str, Any] = {}
    for k, v in schema.items():
        if k in _STRIP_META_KEYS:
            continue
        if k == "properties" and isinstance(v, dict):
            # Inside `properties`, the dict keys are user field names — do
            # NOT run them through the metadata-key filter; just normalize
            # each property's value schema.
            out[k] = {
                prop_name: (
                    _normalize_schema(prop_schema)
                    if isinstance(prop_schema, dict)
                    else prop_schema
                )
                for prop_name, prop_schema in v.items()
            }
        elif isinstance(v, dict):
            out[k] = _normalize_schema(v)
        elif isinstance(v, list):
            out[k] = [_normalize_schema(x) if isinstance(x, dict) else x for x in v]
        else:
            out[k] = v
    return out


class ChatGeminiCloudCode(BaseChatModel):
    """LangChain chat model backed by Google's Code Assist endpoint via OAuth."""

    model_name: str = Field(default="gemini-2.5-pro")
    temperature: float = Field(default=0.2)
    max_output_tokens: int = Field(default=4096)
    timeout_seconds: int = Field(default=120)

    # Set by ``bind_tools(...)``. Stored as raw dicts so we can serialize.
    _function_declarations: list[dict[str, Any]] = []
    _project_id: str | None = None

    class Config:
        arbitrary_types_allowed = True

    # -- LangChain plumbing --------------------------------------------------
    @property
    def _llm_type(self) -> str:
        return "gemini-cloudcode"

    def bind_tools(self, tools: Sequence[Any], **_: Any) -> "ChatGeminiCloudCode":
        # Clone so successive .bind_tools calls don't accumulate.
        new = self.model_copy()
        new._function_declarations = _tools_to_function_declarations(tools)
        return new

    # -- inference ----------------------------------------------------------
    def _project(self) -> str:
        if not self._project_id:
            self._project_id = onboard_project()
        return self._project_id

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {get_valid_access_token()}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": CODE_ASSIST_USER_AGENT,
            "X-Goog-Api-Client": "gl-python/surajclaw",
            "x-activity-request-id": str(uuid.uuid4()),
        }

    def _build_request(self, messages: Sequence[BaseMessage]) -> dict[str, Any]:
        contents, system = _messages_to_gemini(messages)
        inner: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": self.temperature,
                "maxOutputTokens": self.max_output_tokens,
            },
        }
        if system:
            inner["systemInstruction"] = {"parts": [{"text": system}]}
        if self._function_declarations:
            inner["tools"] = [{"functionDeclarations": self._function_declarations}]
        return {
            "project": self._project(),
            "model": self.model_name,
            "user_prompt_id": str(uuid.uuid4()),
            "request": inner,
        }

    # Total wall-clock budget for retry-on-429 across one logical call. Three
    # short waits chained add up to ~90s which is plenty for the typical
    # "reset after Xs" we see from Google.
    _retry_max_seconds: int = 90
    _retry_max_attempts: int = 3

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        body = self._build_request(messages)
        url = f"{CODE_ASSIST_ENDPOINT}/v1internal:generateContent"
        payload = self._post_with_retry(url, body)
        ai = self._payload_to_ai_message(payload)
        return ChatResult(generations=[ChatGeneration(message=ai)])

    def _post_with_retry(self, url: str, body: dict[str, Any]) -> dict[str, Any]:
        import time as _time

        budget = self._retry_max_seconds
        for attempt in range(1, self._retry_max_attempts + 1):
            with httpx.Client(timeout=self.timeout_seconds) as client:
                r = client.post(url, headers=self._headers(), json=body)
            if r.status_code != 429 or attempt == self._retry_max_attempts:
                self._raise_for_status(r)
                return r.json()
            wait = _retry_wait_seconds(r, budget)
            if wait is None:
                self._raise_for_status(r)
                return r.json()
            logger.info(
                "cloudcode-pa 429; sleeping %.1fs then retrying (attempt %d)",
                wait, attempt,
            )
            _time.sleep(wait)
            budget -= int(wait)
            if budget <= 0:
                self._raise_for_status(r)
                return r.json()
        # Unreachable; loop returns earlier.
        raise RuntimeError("retry loop exhausted")

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        import time as _time

        body = self._build_request(messages)
        url = f"{CODE_ASSIST_ENDPOINT}/v1internal:streamGenerateContent?alt=sse"
        budget = self._retry_max_seconds
        for attempt in range(1, self._retry_max_attempts + 1):
            with httpx.Client(timeout=self.timeout_seconds) as client:
                with client.stream("POST", url, headers=self._headers(), json=body) as r:
                    if r.status_code == 429 and attempt < self._retry_max_attempts:
                        wait = _retry_wait_seconds(r, budget)
                        if wait is not None:
                            logger.info(
                                "cloudcode-pa stream 429; sleeping %.1fs then retrying (attempt %d)",
                                wait, attempt,
                            )
                            _time.sleep(wait)
                            budget -= int(wait)
                            if budget > 0:
                                continue
                    self._raise_for_status(r)
                    buf = ""
                    for line in r.iter_lines():
                        if not line:
                            continue
                        if isinstance(line, bytes):
                            line = line.decode("utf-8", errors="replace")
                        if not line.startswith("data:"):
                            continue
                        chunk_raw = line[len("data:"):].strip()
                        if not chunk_raw or chunk_raw == "[DONE]":
                            continue
                        try:
                            payload = json.loads(chunk_raw)
                        except json.JSONDecodeError:
                            buf += chunk_raw
                            try:
                                payload = json.loads(buf)
                                buf = ""
                            except json.JSONDecodeError:
                                continue
                        ai = self._payload_to_ai_message(payload, chunk=True)
                        chunk = ChatGenerationChunk(message=ai)
                        if run_manager:
                            text = _message_text(ai)
                            if text:
                                run_manager.on_llm_new_token(text, chunk=chunk)
                        yield chunk
                    return  # success — don't loop into the retry attempt

    # -- helpers ------------------------------------------------------------
    @staticmethod
    def _raise_for_status(r: httpx.Response) -> None:
        if r.status_code < 400:
            return
        # For streamed responses (``client.stream(...)``) the body isn't
        # automatically buffered. Materialize it before touching .text/.json
        # so we get a useful diagnostic instead of ``ResponseNotRead``.
        try:
            r.read()
        except Exception:  # noqa: BLE001
            pass
        try:
            body = r.json()
        except Exception:  # noqa: BLE001
            try:
                body = r.text[:500]
            except Exception:  # noqa: BLE001
                body = f"<status={r.status_code}, body unreadable>"
        logger.warning("cloudcode-pa %s -> %s: %s", r.request.url, r.status_code, body)
        if r.status_code == 429:
            retry = r.headers.get("Retry-After", "")
            hint = f" (Retry-After: {retry})" if retry else ""
            raise RuntimeError(
                "Gemini Code Assist rate-limited (HTTP 429). Your Google AI / "
                "Gemini subscription quota is exhausted for this window; "
                f"wait a minute and try again{hint}."
            )
        if r.status_code == 401:
            raise RuntimeError(
                "Gemini Code Assist returned 401 — OAuth token rejected. "
                "Run `python manage.py gemini_login` to re-authenticate."
            )
        r.raise_for_status()

    def _payload_to_ai_message(
        self, payload: dict[str, Any], *, chunk: bool = False
    ) -> AIMessage:
        # Code Assist wraps the raw Gemini response in {"response": {...}}.
        inner = payload.get("response") or payload
        candidates = inner.get("candidates") or []
        text_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        for cand in candidates:
            content = (cand.get("content") or {}).get("parts") or []
            for part in content:
                if "text" in part and part["text"]:
                    text_parts.append(part["text"])
                fc = part.get("functionCall")
                if fc:
                    tool_calls.append({
                        "name": fc.get("name", ""),
                        "args": fc.get("args") or {},
                        "id": fc.get("name", "") + "-" + uuid.uuid4().hex[:8],
                    })
        text = "".join(text_parts)
        if chunk:
            # AIMessageChunk merges tool calls via ``tool_call_chunks`` when
            # chunks are concatenated with ``+``. Setting ``.tool_calls``
            # directly on a chunk is silently dropped at aggregation time,
            # which is why earlier versions of this client lost every
            # function-call response from the Gemini stream.
            chunks = [
                {
                    "name": tc["name"],
                    "args": (
                        json.dumps(tc["args"])
                        if isinstance(tc["args"], (dict, list))
                        else (tc["args"] or "")
                    ),
                    "id": tc["id"],
                    "index": i,
                    "type": "tool_call_chunk",
                }
                for i, tc in enumerate(tool_calls)
            ]
            ai: AIMessage = AIMessageChunk(content=text, tool_call_chunks=chunks)
        else:
            ai = AIMessage(content=text)
            if tool_calls:
                ai.tool_calls = tool_calls  # type: ignore[assignment]
        return ai
