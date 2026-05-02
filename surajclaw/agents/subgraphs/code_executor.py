"""Code executor specialized ReAct agent graph."""
from __future__ import annotations

from agents.state import AgentState
from agents.subgraphs.reactive import run_react_agent
from tools.registry import get_langchain_tools


SYSTEM_PROMPT = """You are SurajClaw's Code Executor specialist.

Use only sandbox tools for shell commands, Python, file reads/writes, and tests.
Extract the command or code from the user's natural language request before
running it. Summarize stdout, stderr, exit codes, and any next debugging step.
"""


def build_code_executor_graph():
    from langgraph.graph import END, StateGraph

    graph = StateGraph(AgentState)
    graph.add_node("code_executor", _code_executor_node)
    graph.set_entry_point("code_executor")
    graph.add_edge("code_executor", END)
    return graph.compile()


def _code_executor_node(state: AgentState) -> AgentState:
    return run_react_agent(
        state=state,
        agent_id="code_executor",
        system_prompt=SYSTEM_PROMPT,
        tools=get_langchain_tools("code_executor", session_id=state["session_id"]),
    )
