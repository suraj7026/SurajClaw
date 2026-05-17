"""Notes specialist subgraph (explicit agent_llm + tool_executor)."""
from __future__ import annotations

from agents.registry import get_agent
from agents.subgraphs.reactive import build_agent_subgraph
from tools.registry import get_langchain_tools


def build_notes_graph():
    definition = get_agent("notes")
    return build_agent_subgraph(
        "notes",
        definition.system_prompt,
        get_langchain_tools("notes"),
        max_loops=definition.max_steps,
    )
