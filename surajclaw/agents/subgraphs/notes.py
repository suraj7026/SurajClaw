"""Notes/research specialized ReAct agent graph."""
from __future__ import annotations

from agents.state import AgentState
from agents.subgraphs.reactive import run_react_agent
from tools.registry import get_langchain_tools


SYSTEM_PROMPT = """You are SurajClaw's Notes Agent.

Search existing notes before creating duplicates. For research tasks, search the
web when needed, synthesize the useful facts, and write clear Markdown notes.
Keep notes concise, source-aware, and easy to retrieve later.
"""


def build_notes_graph():
    from langgraph.graph import END, StateGraph

    graph = StateGraph(AgentState)
    graph.add_node("notes", _notes_node)
    graph.set_entry_point("notes")
    graph.add_edge("notes", END)
    return graph.compile()


def _notes_node(state: AgentState) -> AgentState:
    return run_react_agent(
        state=state,
        agent_id="notes",
        system_prompt=SYSTEM_PROMPT,
        tools=get_langchain_tools("notes", session_id=state["session_id"]),
    )
