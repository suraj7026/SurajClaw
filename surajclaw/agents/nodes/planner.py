"""Planner node: decompose the user message into sub-tasks.

The planner pulls semantic context from memory, asks the LLM to emit a
structured plan, and writes it into state as a list of
`{"step": N, "goal": "...", "tools": [...]}` dicts.
"""
from __future__ import annotations

import logging

from agents.model_router import build_llm, route
from agents.state import AgentState

logger = logging.getLogger(__name__)


def planner_node(state: AgentState) -> AgentState:
    user_msg = state.get("user_message", "")

    # Pull memory context if available. This is best-effort — missing tables
    # at early deployment phases shouldn't crash the planner.
    try:
        from memory.services import context_loader

        state["context"] = {k: [str(v) for v in vs] for k, vs in context_loader(user_msg, 2).items()}
    except (ImportError, Exception) as exc:  # noqa: BLE001
        logger.debug("planner: memory context unavailable (%s)", exc)
        state["context"] = {}

    choice = route(user_msg, requires_tools=True)
    logger.info("planner: using %s (%s) — %s", choice.provider, choice.model, choice.reason)

    try:
        llm = build_llm(choice)
        prompt = (
            "You are SurajClaw's planner. Given the user request below, produce a "
            "short numbered plan of 1-4 concrete steps. Each step should be one "
            "sentence. Do not execute anything yet.\n\n"
            f"Request: {user_msg}"
        )
        resp = llm.invoke(prompt)
        text = resp.content if hasattr(resp, "content") else str(resp)
    except (ImportError, RuntimeError, ValueError) as exc:
        logger.warning("planner LLM unavailable (%s); using passthrough plan", exc)
        text = f"1. Answer the user directly: {user_msg}"

    plan = [
        {"step": i + 1, "goal": line.strip().lstrip("0123456789.)- "), "tools": []}
        for i, line in enumerate(text.splitlines())
        if line.strip()
    ]
    state["plan"] = plan or [{"step": 1, "goal": user_msg, "tools": []}]
    state["current_step"] = 0
    return state
