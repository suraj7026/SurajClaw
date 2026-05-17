"""Custom subagent factory.

Custom agents registered at runtime via ``agents.registry.register_custom_agent``
get the same explicit ``agent_llm`` + ``tool_executor`` shape as the built-in
specialists, restricted to whatever ``allowed_tools`` were passed.
"""
from __future__ import annotations

from agents.subgraphs.reactive import build_agent_subgraph
from tools.registry import get_langchain_tools


def build_custom_graph(agent_id: str, system_prompt: str):
    return build_agent_subgraph(
        agent_id,
        system_prompt,
        get_langchain_tools(agent_id),
    )
