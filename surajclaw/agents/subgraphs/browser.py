"""Browser Agent subgraph.

Wraps the Playwright MCP server tools (registered under ``mcp.playwright.*``
by the MCP client at startup) in the standard reactive agent loop. The
agent is invoked via ``ROUTE: BROWSER`` from the General Agent.
"""
from __future__ import annotations

from agents.registry import get_agent
from agents.subgraphs.reactive import build_agent_subgraph
from tools.registry import get_langchain_tools


def build_browser_graph():
    definition = get_agent("browser")
    return build_agent_subgraph(
        "browser",
        definition.system_prompt,
        get_langchain_tools("browser"),
        max_loops=definition.max_steps,
    )
