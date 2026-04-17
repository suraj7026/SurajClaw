"""Typed agent state shared across LangGraph nodes.

Using `TypedDict` with `Annotated` reducers so LangGraph can merge state
updates from parallel branches without clobbering.
"""
from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langgraph.graph.message import add_messages


class AgentState(TypedDict, total=False):
    """State carried between graph nodes.

    Keep this schema minimal — new fields cost memory per message and add
    serialization overhead. Prefer storing bulky context in the DB and
    referencing it by ID here.
    """

    session_id: str
    source: str  # telegram / web / cron / trigger
    user_message: str
    plan: list[dict[str, Any]]  # sub-tasks produced by planner
    current_step: int
    tool_calls: list[dict[str, Any]]
    tool_results: list[dict[str, Any]]
    context: dict[str, Any]  # notes + entities + session embeddings
    messages: Annotated[list[dict[str, Any]], add_messages]
    reflection: str
    final_response: str
