"""Coding Agent subgraph.

Wraps the Google-AI coding spawners (`coding.gemini_cli_run` and
`coding.antigravity_run`) plus light sandbox read tools in the standard
reactive loop. Invoked via ``ROUTE: CODE`` from the General Agent.
"""
from __future__ import annotations

from agents.registry import get_agent
from agents.subgraphs.reactive import build_agent_subgraph
from tools.registry import get_langchain_tools


def build_coding_graph():
    definition = get_agent("coding")
    return build_agent_subgraph(
        "coding",
        definition.system_prompt,
        get_langchain_tools("coding"),
        max_loops=definition.max_steps,
    )
