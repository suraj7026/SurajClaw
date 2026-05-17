"""Top-level multi-agent orchestrator graph (WaqtAgent style).

Wires the four built-in specialist subgraphs into one ``StateGraph`` with
explicit nodes and ``add_conditional_edges`` controlling routing -- mirroring
the shape of ``Vyom_watches/WaqtAgent.py:Waqt`` (DEBRIEFER + DEBRIEFER_TOOL_EXECUTOR
+ SQL_EXECUTOR + DATA_INTERPRETER + PLOT).

Flow::

    entry -> GENERAL (subgraph: agent_llm + tool_executor + loop)
          -> route_after_general:
               "ANSWER"                  -> END
               "ROUTE_GOOGLE_WORKSPACE"  -> GOOGLE_WORKSPACE subgraph -> END
               "ROUTE_CODE_EXECUTOR"     -> CODE_EXECUTOR    subgraph -> END
               "ROUTE_NOTES"             -> NOTES            subgraph -> END

The General Agent emits ``ROUTE: <TARGET>`` on its own line as the last line
of its final assistant message when it wants to delegate; ``route_after_general``
parses the marker and returns the matching edge label. Otherwise the General
Agent's own answer is the user-facing response.

A ``requested_agent`` directive (set by the chat consumer when the user picks
an agent explicitly) bypasses GENERAL entirely and jumps to that specialist.
"""
from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage

from agents.state import AgentState

logger = logging.getLogger(__name__)


ROUTE_PATTERN = re.compile(r"(?mi)^\s*ROUTE:\s*([A-Z_]+)\s*$")

# Mapping of registry agent_id -> top-level node name. Anything not in this map
# can't be reached from the General Agent's ROUTE: tag (custom agents still
# work through `agents.invocation.invoke_agent` directly).
ROUTE_TARGETS = {
    "GOOGLE_WORKSPACE": "GOOGLE_WORKSPACE",
    "CODE_EXECUTOR": "CODE_EXECUTOR",
    "NOTES": "NOTES",
    "BROWSER": "BROWSER",
    "CODE": "CODE",
}


def _last_ai_text(messages: list[BaseMessage]) -> str:
    for m in reversed(messages or []):
        if isinstance(m, AIMessage):
            content = m.content
            if isinstance(content, list):
                content = "".join(
                    part.get("text", "") if isinstance(part, dict) else str(part)
                    for part in content
                )
            return str(content or "")
    return ""


def _strip_route_tag(text: str) -> str:
    return ROUTE_PATTERN.sub("", text).rstrip()


def route_after_general(state: AgentState) -> str:
    """Inspect the General Agent's final AIMessage for a ROUTE: <TARGET> tag."""
    requested = state.get("requested_agent")
    if requested:
        target = requested.upper()
        if target in ROUTE_TARGETS:
            return f"ROUTE_{target}"
    text = _last_ai_text(state.get("messages") or [])
    m = ROUTE_PATTERN.search(text)
    if not m:
        return "ANSWER"
    target = m.group(1).strip().upper()
    if target not in ROUTE_TARGETS:
        return "ANSWER"
    return f"ROUTE_{target}"


def _initial_substate(parent: AgentState, user_message: str) -> dict[str, Any]:
    """Build a fresh state for a specialist subgraph from the parent state.

    ``messages`` is COPIED from the parent so prior turns of the WebSocket
    session (loaded in ``agents.graph._load_prior_messages``) reach the
    LLM. Resetting it to ``[]`` made the model forget every previous turn
    and confabulate ("I don't know your favorite color" right after being
    told).
    """
    definition_max = parent.get("max_loops") or parent.get("max_steps") or 8
    return {
        "user_message": user_message,
        "messages": list(parent.get("messages") or []),
        "tool_call_log": [],
        "loop_count": 0,
        "max_loops": definition_max,
        "active_agent": parent.get("active_agent"),
        "account_label": parent.get("account_label"),
        "context": parent.get("context") or {},
        "session_id": parent.get("session_id", ""),
        "source": parent.get("source", "web"),
    }


@lru_cache(maxsize=8)
def _compiled_subgraph(agent_id: str):
    """Cache compiled per-agent subgraphs so we don't rebuild on every turn."""
    from agents.registry import get_agent

    return get_agent(agent_id).graph_factory()


def _emit_entered(state: AgentState, agent_id: str) -> None:
    on_event = (state.get("context") or {}).get("on_event")
    if on_event:
        try:
            on_event({"type": "node_entered", "node": agent_id.upper()})
        except Exception:  # noqa: BLE001 -- streaming is best-effort
            pass


def _general_node(state: AgentState) -> dict[str, Any]:
    _emit_entered(state, "general")
    sub = _compiled_subgraph("general")
    sub_state = _initial_substate(state, state.get("user_message", ""))
    out = sub.invoke(sub_state)
    text = _last_ai_text(out.get("messages") or [])
    final = _strip_route_tag(text) or text
    return {
        "active_agent": "general",
        "final_response": final,
        "tool_call_log": out.get("tool_call_log", []),
        "messages": out.get("messages", []),
        "model_used": out.get("model_used"),
    }


def _make_specialist_node(agent_id: str):
    def node(state: AgentState) -> dict[str, Any]:
        _emit_entered(state, agent_id)
        sub = _compiled_subgraph(agent_id)
        general_text = _strip_route_tag(_last_ai_text(state.get("messages") or []))
        task = general_text.strip() or state.get("user_message", "")
        sub_state = _initial_substate(state, task)
        out = sub.invoke(sub_state)
        text = _last_ai_text(out.get("messages") or []) or "(no output)"
        return {
            "active_agent": agent_id,
            "final_response": text,
            "tool_call_log": out.get("tool_call_log", []),
            "messages": out.get("messages", []),
            "model_used": out.get("model_used"),
        }

    node.__name__ = f"_{agent_id}_node"
    return node


def build_orchestrator_graph():
    """Compile the top-level multi-agent StateGraph."""
    from langgraph.graph import END, StateGraph

    g = StateGraph(AgentState)
    g.add_node("GENERAL", _general_node)
    g.add_node("GOOGLE_WORKSPACE", _make_specialist_node("google_workspace"))
    g.add_node("CODE_EXECUTOR", _make_specialist_node("code_executor"))
    g.add_node("NOTES", _make_specialist_node("notes"))
    g.add_node("BROWSER", _make_specialist_node("browser"))
    g.add_node("CODE", _make_specialist_node("coding"))

    g.set_entry_point("GENERAL")
    g.add_conditional_edges(
        "GENERAL",
        route_after_general,
        {
            "ANSWER": END,
            "ROUTE_GOOGLE_WORKSPACE": "GOOGLE_WORKSPACE",
            "ROUTE_CODE_EXECUTOR": "CODE_EXECUTOR",
            "ROUTE_NOTES": "NOTES",
            "ROUTE_BROWSER": "BROWSER",
            "ROUTE_CODE": "CODE",
        },
    )
    g.add_edge("GOOGLE_WORKSPACE", END)
    g.add_edge("CODE_EXECUTOR", END)
    g.add_edge("NOTES", END)
    g.add_edge("BROWSER", END)
    g.add_edge("CODE", END)
    return g.compile()


def state_debug_json(state: AgentState) -> str:
    return json.dumps({"trace": state.get("agent_trace", [])}, default=str)
