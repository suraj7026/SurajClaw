"""Google Workspace specialized ReAct agent graph."""
from __future__ import annotations

from agents.state import AgentState
from agents.subgraphs.reactive import run_react_agent
from tools.registry import get_langchain_tools


SYSTEM_PROMPT = """You are SurajClaw's Google Workspace specialist.

Use Google Workspace tools for Gmail, Calendar, Tasks, Drive, Docs, Sheets, and
Contacts. Prefer read/search before write/update/delete. Gmail is read-only in
this system. Use the supplied account_label when a tool requires an account.
"""


def build_google_workspace_graph():
    from langgraph.graph import END, StateGraph

    graph = StateGraph(AgentState)
    graph.add_node("google_workspace", _google_workspace_node)
    graph.set_entry_point("google_workspace")
    graph.add_edge("google_workspace", END)
    return graph.compile()


def _google_workspace_node(state: AgentState) -> AgentState:
    return run_react_agent(
        state=state,
        agent_id="google_workspace",
        system_prompt=SYSTEM_PROMPT,
        tools=get_langchain_tools("google_workspace", session_id=state["session_id"]),
    )
