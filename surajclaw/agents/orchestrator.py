"""Thin orchestrator that invokes the General Agent by default."""
from __future__ import annotations

import json

from agents.invocation import invoke_agent
from agents.state import AgentState
from agents.types import AgentInvocation


def build_orchestrator_graph():
    """Build a single-step graph that delegates to General or a requested agent."""
    from langgraph.graph import END, StateGraph

    graph = StateGraph(AgentState)
    graph.add_node("invoke_agent", invoke_agent_node)

    graph.set_entry_point("invoke_agent")
    graph.add_edge("invoke_agent", END)
    return graph.compile()


def invoke_agent_node(state: AgentState) -> AgentState:
    agent_id = state.get("requested_agent") or "general"
    state["active_agent"] = agent_id
    state["step_count"] = state.get("step_count", 0) + 1
    result = invoke_agent(
        AgentInvocation(
            session_id=state["session_id"],
            source=state.get("source", "web"),
            agent_id=agent_id,
            task=state.get("user_message", ""),
            account_label=(state.get("context") or {}).get("account_label"),
            context={
                **(state.get("context") or {}),
                "agent_results": state.get("agent_results", []),
            },
        )
    )
    row = result.__dict__
    state.setdefault("agent_results", []).append(row)
    state.setdefault("agent_trace", []).append(
        {"step": state["step_count"], "agent": agent_id, "status": result.status}
    )
    state["last_agent_result"] = row
    state["final_response"] = result.output
    state["agent_result"] = row
    state["model_used"] = result.structured.get("model_used")
    return state


def state_debug_json(state: AgentState) -> str:
    return json.dumps({"trace": state.get("agent_trace", [])}, default=str)
