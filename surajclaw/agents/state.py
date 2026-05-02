"""Typed agent state shared across LangGraph nodes.

Using `TypedDict` with `Annotated` reducers so LangGraph can merge state
updates from parallel branches without clobbering.
"""
from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langchain_core.messages import BaseMessage

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
    tool_calls: list[dict[str, Any]]
    tool_results: list[dict[str, Any]]
    context: dict[str, Any]  # notes + entities + session embeddings
    messages: list[dict[str, Any]]
    agent_messages: Annotated[list[BaseMessage], add_messages]
    final_response: str
    active_agent: str
    requested_agent: str | None
    agent_trace: list[dict[str, Any]]
    agent_results: list[dict[str, Any]]
    last_agent_result: dict[str, Any]
    pending_approval: dict[str, Any] | None
    done: bool
    step_count: int
    max_steps: int
    account_label: str | None
    agent_result: dict[str, Any]
    model_used: str | None
