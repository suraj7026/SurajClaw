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
    _persist(session_id, role="user", content=message, source=source)
    model_used = None

    # Adapter so the subgraph only has to call one callback regardless of
    # which surface invoked the turn. Token-only callers see token frames
    # downgraded to bare strings; everyone else sees structured frames.
    def dispatch(payload: dict[str, Any]) -> None:
        if on_event is not None:
            _emit_event(on_event, payload)
        if on_token is not None and payload.get("type") == "token":
            _emit_event(on_token, payload.get("content", ""))  # type: ignore[arg-type]

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
            "context": {
                "directives": directives or {},
                "on_event": dispatch,
            },
            "messages": [],
            "agent_messages": [],
            "step_count": 0,
            "done": False,
        }
        state = graph.invoke(initial)
        final = state.get("final_response", "")
        model_used = state.get("model_used")
    except (ImportError, RuntimeError, ValueError) as exc:
        # Defensive: don't let agent errors crash the worker. Log,
        # persist the error as an assistant message, and return.
        logger.exception("agent turn failed")
        final = f"[agent error: {exc}]"
        dispatch({"type": "error", "content": final})

    # The reactive subgraph already streamed `token` frames during
    # execution. Emit a single `final` frame so clients that prefer the
    # full text (e.g. logs) have a clean checkpoint without us re-streaming
    # what they already saw token-by-token.
    dispatch({"type": "final", "content": final})

    _persist(
        session_id,
        role="assistant",
        content=final,
        source=source,
        model_used=model_used or "unknown",
    )
    return final
