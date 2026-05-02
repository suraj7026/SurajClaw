"""Common invocation path for direct calls and orchestrator handoffs."""
from __future__ import annotations

from agents.registry import get_agent
from agents.types import AgentInvocation, AgentResult


def invoke_agent(invocation: AgentInvocation) -> AgentResult:
    """Run a registered agent graph and normalize its final result."""
    try:
        definition = get_agent(invocation.agent_id)
    except LookupError as exc:
        return AgentResult(
            agent_id=invocation.agent_id,
            status="failed",
            output=str(exc),
            structured={"error": "unknown_agent"},
        )

    graph = definition.graph_factory()
    context = dict(invocation.context or {})
    prior_results = context.get("agent_results", [])
    if "memory_context" not in context:
        try:
            from memory.services import context_loader

            context["memory_context"] = context_loader(invocation.task)
        except Exception as exc:  # noqa: BLE001 -- memory should not block an agent turn
            context["memory_error"] = str(exc)
    state = {
        "session_id": invocation.session_id,
        "source": invocation.source,
        "active_agent": definition.id,
        "user_message": invocation.task,
        "context": context,
        "account_label": invocation.account_label,
        "step_count": 0,
        "max_steps": definition.max_steps,
        "tool_calls": [],
        "tool_results": [],
        "agent_results": prior_results,
        "agent_trace": [],
        "agent_messages": [],
        "done": False,
    }
    try:
        final_state = graph.invoke(state)
    except Exception as exc:  # noqa: BLE001 -- agent graph errors return to caller
        return AgentResult(
            agent_id=definition.id,
            status="failed",
            output=f"agent graph failed: {exc}",
            structured={"error": type(exc).__name__},
        )

    result = final_state.get("agent_result") or {}
    if isinstance(result, AgentResult):
        return result
    return AgentResult(
        agent_id=definition.id,
        status=result.get("status", "ok"),
        output=result.get("output", final_state.get("final_response", "")),
        structured=result.get("structured", {}),
        next_agent=result.get("next_agent"),
        approval_request_id=result.get("approval_request_id"),
    )
