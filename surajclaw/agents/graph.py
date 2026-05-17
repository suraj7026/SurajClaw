"""Main agent turn entrypoint.

`run_turn(session_id, message, source)` persists the user message, invokes the
general-agent supervisor, persists the assistant response, and forwards
streaming events (LLM tokens + tool activity) to the caller through
``on_event``. The reactive subgraph drives the actual streaming; this module
is just the persistence shell around it.
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

# A frame is a JSON-serializable dict like
#   {"type": "token", "content": "..."}
#   {"type": "tool_call", "name": "...", "args": {...}, "id": "..."}
#   {"type": "tool_result", "name": "...", "content": "...", "id": "..."}
EventCallback = Callable[[dict[str, Any]], Awaitable[None] | None]


async def _await_result(awaitable):
    return await awaitable


def _emit_event(callback: EventCallback | None, payload: dict[str, Any]) -> None:
    """Best-effort dispatch of one stream frame.

    The callback is sync from where we sit (we run inside sync_to_async),
    but the consumer-supplied callback can return an awaitable (it's an
    `async def` on the consumer side). We bridge with async_to_sync.

    Errors here MUST NOT bubble up: streaming is purely advisory; the agent
    turn still succeeds even if the WebSocket is closed.
    """
    if callback is None or not payload:
        return
    try:
        result = callback(payload)
        if inspect.isawaitable(result):
            async_to_sync(_await_result)(result)
    except Exception as exc:  # noqa: BLE001 -- streaming should not break persistence
        logger.debug("event callback failed: %s", exc)


def _session_pk(session_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(session_id))
    except ValueError:
        return uuid.uuid5(uuid.NAMESPACE_URL, f"surajclaw:{session_id}")


def _source_value(source: str) -> str:
    from core.models import Session

    values = {choice.value for choice in Session.Source}
    return source if source in values else Session.Source.WEB


def _load_prior_messages(session_id: str) -> list:
    """Return user/assistant turns from this session as LangChain messages.

    Without this, every WebSocket turn starts with an empty ``messages``
    list and the LLM can't see what it said two messages ago — so it
    confabulates. We exclude tool messages because the tool-call ids no
    longer match across turns and would confuse the reactive subgraph.
    """
    from langchain_core.messages import AIMessage, HumanMessage

    from core.models import Message

    pk = _session_pk(session_id)
    prior: list = []
    qs = (
        Message.objects.filter(
            session_id=pk,
            role__in=[Message.Role.USER, Message.Role.ASSISTANT],
        )
        .order_by("created_at")
        .only("role", "content")
    )
    for m in qs:
        text = m.content or ""
        if m.role == Message.Role.USER:
            prior.append(HumanMessage(content=text))
        else:
            prior.append(AIMessage(content=text))
    return prior


def _persist(
    session_id: str,
    role: str,
    content: str,
    source: str = "web",
    model_used: str | None = None,
) -> None:
    from django.db import transaction
    from django.utils import timezone

    from core.models import Message, Session

    pk = _session_pk(session_id)
    with transaction.atomic():
        session, created = Session.objects.get_or_create(
            id=pk,
            defaults={"source": _source_value(source)},
        )
        # Enforce single-active-session policy: when a brand-new session
        # starts, retire every other live session so the dashboard /
        # sidebar only ever shows the current conversation. We only do
        # this on creation to avoid pointlessly thrashing rows on every
        # message of an existing chat.
        if created:
            Session.objects.filter(is_active=True).exclude(pk=pk).update(
                is_active=False,
                ended_at=timezone.now(),
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
    on_event: EventCallback | None = None,
    on_token: EventCallback | None = None,  # back-compat alias
) -> str:
    """Execute one agent turn, streaming events through ``on_event``.

    ``on_event`` receives a dict frame for every meaningful step:
    ``token`` (LLM chunk), ``tool_call`` (model decided to call a tool),
    ``tool_result`` (tool returned), and a final ``final`` (full response
    text). The consumer forwards these as JSON to the WebSocket.

    ``on_token`` is kept as a legacy hook: callers that pass it get a
    string-only token stream and nothing else. Prefer ``on_event``.

    Returns the final response text (also persisted as a Message row).
    """
    # Load prior turns BEFORE we persist the current user message so the
    # initial agent state mirrors the conversation as it stood *before*
    # this question — then we append the current message ourselves.
    prior_messages = _load_prior_messages(session_id)
    _persist(session_id, role="user", content=message, source=source)
    from langchain_core.messages import HumanMessage as _HM

    prior_messages.append(_HM(content=message))
    model_used = None

    # Adapter so the subgraph only has to call one callback regardless of
    # which surface invoked the turn. Token-only callers see token frames
    # downgraded to bare strings; everyone else sees structured frames.
    def dispatch(payload: dict[str, Any]) -> None:
        if on_event is not None:
            _emit_event(on_event, payload)
        if on_token is not None and payload.get("type") == "token":
            _emit_event(on_token, payload.get("content", ""))  # type: ignore[arg-type]

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
            "tool_call_log": [],
            "context": {
                "directives": directives or {},
                "on_event": dispatch,
            },
            "messages": prior_messages,
            "agent_messages": [],
            "step_count": 0,
            "loop_count": 0,
            "max_loops": 8,
            "done": False,
        }
        # Drive the orchestrator with stream_mode="updates" so we see one
        # frame per node finish. Tool-call activity has already been
        # forwarded via state["context"]["on_event"] from inside the
        # subgraph nodes (see agents/subgraphs/reactive.py); here we only
        # mirror node boundaries and capture the latest final_response.
        active_agent = "general"
        for update in graph.stream(initial, stream_mode="updates"):
            if not isinstance(update, dict):
                continue
            for node_name, node_state in update.items():
                if not isinstance(node_state, dict):
                    continue
                dispatch({"type": "node_update", "node": node_name})
                if node_state.get("final_response"):
                    final = node_state["final_response"]
                if node_state.get("active_agent"):
                    active_agent = node_state["active_agent"]
                if node_state.get("model_used"):
                    model_used = node_state["model_used"]
        if not final:
            final = "(no response)"
    except (ImportError, RuntimeError, ValueError) as exc:
        # Defensive: don't let agent errors crash the worker. Log,
        # persist the error as an assistant message, and return.
        logger.exception("agent turn failed")
        final = f"[agent error: {exc}]"
        dispatch({"type": "error", "content": final})

    dispatch({"type": "final", "content": final})

    _persist(
        session_id,
        role="assistant",
        content=final,
        source=source,
        model_used=model_used or "unknown",
    )

    # Update the session-level semantic index after every response so
    # memory.search has fresh material for the *next* turn (in-session
    # context is handled separately by _load_prior_messages above).
    # Prefer Celery so we don't add latency to the WS turn; if the worker
    # is down or the broker rejects us, fall back to a synchronous write
    # — the user explicitly wants memory updated after every response.
    pk = str(_session_pk(session_id))
    try:
        from scheduler.tasks import index_session_embedding

        async_result = index_session_embedding.delay(pk)
        logger.info(
            "memory: enqueued index_session_embedding session=%s task_id=%s",
            session_id, async_result.id,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "memory: Celery enqueue failed (%s); writing embedding inline",
            exc,
        )
        try:
            from scheduler.tasks import index_session_embedding as _ise

            _ise(pk)
            logger.info("memory: wrote embedding inline for session=%s", session_id)
        except Exception as exc2:  # noqa: BLE001
            logger.error(
                "memory: inline embedding write failed: %s",
                exc2, exc_info=True,
            )

    return final
