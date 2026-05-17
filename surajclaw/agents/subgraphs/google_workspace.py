"""Google Workspace specialist subgraph (explicit agent_llm + tool_executor)."""
from __future__ import annotations

from agents.registry import get_agent
from agents.subgraphs.reactive import build_agent_subgraph
from tools.registry import get_langchain_tools


def build_google_workspace_graph():
    definition = get_agent("google_workspace")
    return build_agent_subgraph(
        "google_workspace",
        definition.system_prompt,
        get_langchain_tools("google_workspace"),
        max_loops=definition.max_steps,
    )
