"""General Agent supervisor subgraph."""
from __future__ import annotations

from agents.state import AgentState
from agents.subgraphs.reactive import run_react_agent
from agents.types import AgentInvocation, AgentResult
from tools.registry import get_langchain_tools


SYSTEM_PROMPT = """You are SurajClaw's General Agent.

You are the default brain for a single-user personal AI system. Answer directly
when no tool is needed. Use direct tools for web search, memory lookup,
workspace files, and sandboxed code execution. Delegate specialized work to the
Google Workspace, Code Executor, or Notes agents when they are better suited.
Do not claim an external action succeeded unless a tool or subagent confirms it.
"""


def build_general_graph():
    from langgraph.graph import END, StateGraph

    graph = StateGraph(AgentState)
    graph.add_node("general", _general_node)
    graph.set_entry_point("general")
    graph.add_edge("general", END)
    return graph.compile()


def _general_node(state: AgentState) -> AgentState:
    session_id = state["session_id"]
    tools = get_langchain_tools("general", session_id=session_id)
    tools.extend(_subagent_tools(state))
    return run_react_agent(
        state=state,
        agent_id="general",
        system_prompt=SYSTEM_PROMPT,
        tools=tools,
    )


def _subagent_tools(state: AgentState):
    from langchain_core.tools import StructuredTool

    session_id = state["session_id"]
    source = state.get("source", "web")
    context = dict(state.get("context") or {})

    def invoke_google_workspace(task: str, account_label: str = "default") -> str:
        """Delegate Google Workspace tasks like Gmail, Calendar, Drive, Docs, Sheets, Tasks, and Contacts."""
        return _invoke(
            session_id=session_id,
            source=source,
            agent_id="google_workspace",
            task=task,
            context=context,
            account_label=account_label or state.get("account_label") or "default",
        )

    def invoke_code_executor(task: str) -> str:
        """Delegate code execution, shell commands, debugging, or test runs to the sandbox specialist."""
        return _invoke(
            session_id=session_id,
            source=source,
            agent_id="code_executor",
            task=task,
            context=context,
            account_label=state.get("account_label"),
        )

    def invoke_notes_agent(task: str) -> str:
        """Delegate note writing, note search, or research-to-note tasks."""
        return _invoke(
            session_id=session_id,
            source=source,
            agent_id="notes",
            task=task,
            context=context,
            account_label=state.get("account_label"),
        )

    return [
        StructuredTool.from_function(invoke_google_workspace),
        StructuredTool.from_function(invoke_code_executor),
        StructuredTool.from_function(invoke_notes_agent),
    ]


def _invoke(
    *,
    session_id: str,
    source: str,
    agent_id: str,
    task: str,
    context: dict,
    account_label: str | None,
) -> str:
    from agents.invocation import invoke_agent

    result: AgentResult = invoke_agent(
        AgentInvocation(
            session_id=session_id,
            source=source,
            agent_id=agent_id,
            task=task,
            account_label=account_label,
            context={**context, "delegated_by": "general"},
        )
    )
    return f"{agent_id} [{result.status}]: {result.output}"
