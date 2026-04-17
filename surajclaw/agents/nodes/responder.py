"""Responder node: compose the final natural-language reply.

Consumes the tool results and plan, calls the routed LLM, stores the
result in `state["final_response"]`.
"""
from __future__ import annotations

import logging

from agents.model_router import build_llm, route
from agents.state import AgentState

logger = logging.getLogger(__name__)


def responder_node(state: AgentState) -> AgentState:
    user_msg = state.get("user_message", "")
    plan = state.get("plan", [])
    tool_results = state.get("tool_results", [])

    context_snippet = "\n".join(
        f"- step {i + 1}: {r.get('output', '')}"
        for i, r in enumerate(tool_results)
    ) or "(no tool output)"

    prompt = (
        "You are SurajClaw, a concise helpful assistant. Compose a final reply "
        "to the user based on the plan and the tool results below.\n\n"
        f"User request: {user_msg}\n\n"
        f"Plan steps: {[p['goal'] for p in plan]}\n\n"
        f"Tool results:\n{context_snippet}\n\n"
        "Reply in at most 3 short paragraphs."
    )

    choice = route(prompt, requires_tools=False)
    try:
        llm = build_llm(choice)
        resp = llm.invoke(prompt)
        text = resp.content if hasattr(resp, "content") else str(resp)
    except (ImportError, RuntimeError, ValueError) as exc:
        logger.warning("responder LLM unavailable (%s); falling back to echo", exc)
        text = f"(fallback) I got your message: {user_msg}"

    state["final_response"] = text
    return state
