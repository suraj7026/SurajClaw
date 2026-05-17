"""Code executor specialist subgraph (explicit agent_llm + tool_executor)."""
from __future__ import annotations

from agents.registry import get_agent
from agents.subgraphs.reactive import build_agent_subgraph
from tools.registry import get_langchain_tools


def build_code_executor_graph():
    definition = get_agent("code_executor")
    return build_agent_subgraph(
        "code_executor",
        definition.system_prompt,
        get_langchain_tools("code_executor"),
        max_loops=definition.max_steps,
    )
