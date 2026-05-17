"""General Agent subgraph.

Built from the shared ``build_agent_subgraph`` factory: an explicit
``agent_llm`` + ``tool_executor`` loop. Delegation is done by the General
Agent's LLM emitting a ``ROUTE: <TARGET>`` line on its own line as the last
line of its final assistant message; the top-level orchestrator
(`agents/orchestrator.py`) parses that tag and hands off to the matching
specialist subgraph.

The previous ``_subagent_tools`` factory that exposed ``invoke_google_workspace``
etc. as fake ``StructuredTool``s is gone -- routing is graph control flow now,
not tool selection.
"""
from __future__ import annotations

from agents.registry import get_agent
from agents.subgraphs.reactive import build_agent_subgraph
from tools.registry import get_langchain_tools


def build_general_graph():
    definition = get_agent("general")
    return build_agent_subgraph(
        "general",
        definition.system_prompt,
        get_langchain_tools("general"),
        max_loops=definition.max_steps,
    )
