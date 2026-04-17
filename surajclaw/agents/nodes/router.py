"""Router node: pick the best tool for the current plan step."""
from __future__ import annotations

import logging

from agents.state import AgentState

logger = logging.getLogger(__name__)


def router_node(state: AgentState) -> AgentState:
    plan = state.get("plan", [])
    idx = state.get("current_step", 0)
    if idx >= len(plan):
        return state
    step = plan[idx]
    # In the full implementation the LLM picks a tool from the registry.
    # For now we leave `tool_calls` empty; the executor then falls back
    # to a direct LLM response.
    state.setdefault("tool_calls", []).append(
        {"step": step["step"], "tool": None, "args": {}}
    )
    return state
