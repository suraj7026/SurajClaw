"""Custom subagent graph factory."""
from __future__ import annotations

from agents.state import AgentState


def build_custom_graph(agent_id: str, system_prompt: str):
    from langgraph.graph import END, StateGraph

    def _run(state: AgentState) -> AgentState:
        state["agent_result"] = {
            "status": "ok",
            "output": f"{agent_id}: {system_prompt}\n\nTask received: {state.get('user_message', '')}",
            "structured": {"custom_agent": agent_id},
        }
        return state

    graph = StateGraph(AgentState)
    graph.add_node("custom_run", _run)
    graph.set_entry_point("custom_run")
    graph.add_edge("custom_run", END)
    return graph.compile()
