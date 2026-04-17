"""Main LangGraph pipeline: planner -> router -> executor -> reflector -> responder.

`run_turn(session_id, message, source)` is the single entrypoint called
by both the Celery WebSocket handler and the Telegram webhook task.
"""
from __future__ import annotations

import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from agents.state import AgentState

logger = logging.getLogger(__name__)


def _send_token(session_id: str, token: str) -> None:
    """Stream a token back to the web UI via the session's channel group."""
    try:
        layer = get_channel_layer()
        if layer is None:
            return
        async_to_sync(layer.group_send)(
            f"chat.{session_id}",
            {"type": "chat.token", "content": token},
        )
    except (ImportError, RuntimeError) as exc:
        logger.debug("_send_token failed: %s", exc)


def _send_done(session_id: str) -> None:
    try:
        layer = get_channel_layer()
        if layer is None:
            return
        async_to_sync(layer.group_send)(
            f"chat.{session_id}",
            {"type": "chat.done"},
        )
    except (ImportError, RuntimeError) as exc:
        logger.debug("_send_done failed: %s", exc)


def _persist(session_id: str, role: str, content: str, model_used: str | None = None) -> None:
    from core.models import Message, Session

    session, _ = Session.objects.get_or_create(
        id=session_id,
        defaults={"source": Session.Source.WEB},
    )
    Message.objects.create(
        session=session,
        role=role,
        content=content,
        model_used=model_used,
    )


def build_graph():
    """Construct and compile the LangGraph StateGraph.

    Nodes live in `agents/nodes/` and are imported lazily so a minimal
    deployment (no Gemini, no tools) doesn't need all node dependencies.
    """
    from langgraph.graph import END, StateGraph

    from agents.nodes.executor import executor_node
    from agents.nodes.planner import planner_node
    from agents.nodes.reflector import reflector_node
    from agents.nodes.responder import responder_node
    from agents.nodes.router import router_node

    graph = StateGraph(AgentState)
    graph.add_node("planner", planner_node)
    graph.add_node("router", router_node)
    graph.add_node("executor", executor_node)
    graph.add_node("reflector", reflector_node)
    graph.add_node("responder", responder_node)

    graph.set_entry_point("planner")
    graph.add_edge("planner", "router")
    graph.add_edge("router", "executor")
    graph.add_edge("executor", "reflector")

    # Reflector decides whether we're done or need another pass.
    def _after_reflector(state: AgentState) -> str:
        if state.get("current_step", 0) < len(state.get("plan", [])):
            return "router"
        return "responder"

    graph.add_conditional_edges("reflector", _after_reflector)
    graph.add_edge("responder", END)

    return graph.compile()


_compiled = None


def _get_graph():
    global _compiled
    if _compiled is None:
        _compiled = build_graph()
    return _compiled


def run_turn(session_id: str, message: str, source: str = "web") -> str:
    """Execute one agent turn and stream tokens back via Channels.

    Returns the final response text (also persisted as a Message row).
    """
    _persist(session_id, role="user", content=message)

    try:
        graph = _get_graph()
        initial: AgentState = {
            "session_id": session_id,
            "source": source,
            "user_message": message,
            "plan": [],
            "current_step": 0,
            "tool_calls": [],
            "tool_results": [],
            "context": {},
            "messages": [],
        }
        state = graph.invoke(initial)
        final = state.get("final_response", "")
    except (ImportError, RuntimeError, ValueError) as exc:
        # Defensive: don't let agent errors crash the Celery worker. Log,
        # persist the error as an assistant message, and return.
        logger.exception("agent turn failed")
        final = f"[agent error: {exc}]"

    for chunk in final.split(" "):
        _send_token(session_id, chunk + " ")
    _send_done(session_id)

    _persist(session_id, role="assistant", content=final, model_used="router")
    return final
