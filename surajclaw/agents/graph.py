"""Main agent turn entrypoint.

`run_turn(session_id, message, source)` persists the user message, invokes the
general-agent supervisor, persists the assistant response, and streams response
chunks through an optional direct callback.
"""
from __future__ import annotations

import inspect
import logging
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from asgiref.sync import async_to_sync

from agents.state import AgentState

logger = logging.getLogger(__name__)

TokenCallback = Callable[[str], Awaitable[None] | None]


async def _await_result(awaitable):
    return await awaitable


def _emit_token(callback: TokenCallback | None, token: str) -> None:
    if callback is None or not token:
        return
    try:
        result = callback(token)
        if inspect.isawaitable(result):
            async_to_sync(_await_result)(result)
    except Exception as exc:  # noqa: BLE001 -- streaming should not break persistence
        logger.debug("token callback failed: %s", exc)


def _session_pk(session_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(session_id))
    except ValueError:
        return uuid.uuid5(uuid.NAMESPACE_URL, f"surajclaw:{session_id}")


def _source_value(source: str) -> str:
    from core.models import Message, Session

    values = {choice.value for choice in Session.Source}
    return source if source in values else Session.Source.WEB


def _persist(
    session_id: str,
    role: str,
    content: str,
    source: str = "web",
    model_used: str | None = None,
) -> None:
    from core.models import Message, Session

    session, _ = Session.objects.get_or_create(
        id=_session_pk(session_id),
        defaults={"source": _source_value(source)},
    )
    Message.objects.create(
        session=session,
        role=role,
        content=content,
        model_used=model_used,
    )


def build_graph():
    """Construct the main graph-of-graphs orchestrator."""
    from agents.orchestrator import build_orchestrator_graph

    return build_orchestrator_graph()


_compiled = None


def _get_graph():
    global _compiled
    if _compiled is None:
        _compiled = build_graph()
    return _compiled


def run_turn(
    session_id: str,
    message: str,
    source: str = "web",
    directives: dict | None = None,
    on_token: TokenCallback | None = None,
) -> str:
    """Execute one agent turn and stream chunks through ``on_token``.

    ``directives`` carries per-turn overrides parsed from inline ``!key value``
    syntax. Stored on the LangGraph state so agents and tools can
    consult them. ``directives["agent"]`` (if set) directly invokes a
    specific agent; otherwise the General Agent supervisor is invoked.

    Returns the final response text (also persisted as a Message row).
    """
    _persist(session_id, role="user", content=message, source=source)
    model_used: str | None = None
    final = ""

    try:
        graph = _get_graph()
        initial: AgentState = {
            "session_id": session_id,
            "source": source,
            "user_message": message,
            "requested_agent": (directives or {}).get("agent"),
            "tool_calls": [],
            "tool_results": [],
            "agent_results": [],
            "agent_trace": [],
            "context": {"directives": directives or {}},
            "messages": [],
            "agent_messages": [],
            "step_count": 0,
            "done": False,
        }
        state = graph.invoke(initial)
        final = state.get("final_response", "") or ""
        model_used = state.get("model_used")
    except Exception as exc:  # noqa: BLE001 -- agent errors must not kill the WS turn
        logger.exception("agent turn failed")
        final = f"[agent error: {exc}]"

    if final:
        _stream_text(on_token, final)

    _persist(
        session_id,
        role="assistant",
        content=final,
        source=source,
        model_used=model_used or "unknown",
    )
    return final


def _stream_text(on_token: TokenCallback | None, text: str, chunk_size: int = 24) -> None:
    """Emit ``text`` to the client in roughly word-aligned chunks.

    LangGraph's prebuilt ReAct agent doesn't expose mid-turn token deltas
    cleanly through its sync invoke path, so we stream the assembled final
    response in small chunks. This keeps the UI responsive without requiring
    a second pass through ``astream_events``.
    """
    if not on_token or not text:
        return
    buffer: list[str] = []
    size = 0
    for word in text.split(" "):
        piece = (word + " ") if buffer or word else word
        buffer.append(piece)
        size += len(piece)
        if size >= chunk_size:
            _emit_token(on_token, "".join(buffer))
            buffer = []
            size = 0
    if buffer:
        _emit_token(on_token, "".join(buffer))
