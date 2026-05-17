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

    # Direct invocation builds the agent's own per-agent subgraph (the
    # `agent_llm + tool_executor` factory) instead of going through the
    # top-level orchestrator. The `main` agent is special-cased because its
    # graph_factory IS the orchestrator and we don't want recursive routing
    # when a caller explicitly asked for it.
    if definition.id == "main":
        graph = definition.graph_factory()
    else:
        from agents.subgraphs.reactive import build_agent_subgraph
        from tools.registry import get_langchain_tools

        graph = build_agent_subgraph(
            definition.id,
            definition.system_prompt,
            get_langchain_tools(definition.id),
            max_loops=definition.max_steps,
        )

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
        "loop_count": 0,
        "max_loops": definition.max_steps,
        "tool_calls": [],
        "tool_results": [],
        "tool_call_log": [],
        "agent_results": prior_results,
        "agent_trace": [],
        "messages": [],
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
    if not result:
        from agents.subgraphs.reactive import last_ai_text

        output = final_state.get("final_response") or last_ai_text(
            final_state.get("messages") or []
        )
        return AgentResult(
            agent_id=definition.id,
            status="ok",
            output=output,
            structured={"tool_call_log": final_state.get("tool_call_log", [])},
        )
    return AgentResult(
        agent_id=definition.id,
        status=result.get("status", "ok"),
        output=result.get("output", final_state.get("final_response", "")),
        structured=result.get("structured", {}),
        next_agent=result.get("next_agent"),
        approval_request_id=result.get("approval_request_id"),
    )
