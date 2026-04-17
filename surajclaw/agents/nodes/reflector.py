"""Reflector node: advance the plan cursor, extract entities, decide next hop."""
from __future__ import annotations

import logging

from agents.state import AgentState

logger = logging.getLogger(__name__)


def reflector_node(state: AgentState) -> AgentState:
    state["current_step"] = state.get("current_step", 0) + 1
    # Entity extraction (person/project/company mentions) would run here and
    # upsert rows into memory.Entity. Left as a follow-up to avoid a full
    # LLM round-trip for the MVP.
    return state
