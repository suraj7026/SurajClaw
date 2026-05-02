"""Shared LLM + tool ReAct runner for SurajClaw agents.

If `state["context"]["on_event"]` is set, the LangGraph ReAct agent is driven
through `.stream(stream_mode=["messages", "updates"])` so the caller sees:

* `{"type": "token", "content": "..."}` for each LLM token chunk
* `{"type": "tool_call", "name": "...", "args": {...}, "id": "..."}`
  the moment the model decides to call a tool
* `{"type": "tool_result", "name": "...", "content": "...", "id": "..."}`
  when each tool returns

If no callback is attached, we fall back to a plain `.invoke()` so non-chat
callers (cron, REST `/api/agents/<id>/invoke/`) keep working.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Callable

from agents.model_router import build_llm, route
from agents.state import AgentState

logger = logging.getLogger(__name__)


def run_react_agent(
    *,
    state: AgentState,
    agent_id: str,
    system_prompt: str,
    tools: list[Any],
) -> AgentState:
    """Run one ReAct agent invocation and write ``agent_result`` into state."""
    from langchain_core.messages import HumanMessage
    from langgraph.prebuilt import create_react_agent
    from memory.services import format_context

    task = state.get("user_message", "")
    context = state.get("context") or {}
    directives = context.get("directives") or {}
    on_event: Callable[[dict[str, Any]], None] | None = context.get("on_event")

    choice = route(
        task,
        requires_tools=bool(tools),
        complexity_hint=str(directives.get("thinking") or ""),
        session_id=state.get("session_id"),
        directive_model=directives.get("model"),
    )
    llm = build_llm(choice)
    memory_text = format_context(context.get("memory_context") or {})
    prompt = _compose_prompt(system_prompt, memory_text)
    agent = create_react_agent(llm, tools, prompt=prompt)

    config = {"recursion_limit": max(8, state.get("max_steps", 6) * 4)}
    payload = {"messages": [HumanMessage(content=task)]}

    if on_event is None:
        result = agent.invoke(payload, config)
        messages = result.get("messages", [])
    else:
        messages = _stream_react_agent(agent, payload, config, on_event)

    output = _message_content(messages[-1]) if messages else ""
    state["agent_messages"] = messages
    state["final_response"] = output
    state["model_used"] = choice.model
    state["agent_result"] = {
        "status": "ok",
        "output": output,
        "structured": {"model_used": choice.model, "model_reason": choice.reason},
    }
    return state


def _stream_react_agent(
    agent,
    payload: dict[str, Any],
    config: dict[str, Any],
    on_event: Callable[[dict[str, Any]], None],
) -> list[Any]:
    """Drive ``agent.stream`` and forward token + tool frames to ``on_event``.

    LangGraph's multi-mode stream yields ``(mode, chunk)`` tuples where
    ``mode`` is ``"messages"`` or ``"updates"``. We mine each:

    * **messages**: ``(message_chunk, metadata)``. We forward only chunks
      that come from the LLM node (``langgraph_node == "agent"``) because
      the tools node also emits messages and we don't want to double-stream
      tool output as if it were assistant prose.
    * **updates**: ``{node_name: {"messages": [...]}}``. From the ``agent``
      node we read ``tool_calls`` to announce which tool is about to fire;
      from the ``tools`` node we read each ``ToolMessage`` to announce the
      result. We also harvest the final assistant ``AIMessage`` here so the
      caller doesn't need to re-iterate.
    """
    final_messages: list[Any] = []
    streamed_call_ids: set[str] = set()

    try:
        events = agent.stream(payload, config, stream_mode=["messages", "updates"])
    except TypeError:
        # Older LangGraph builds didn't accept a list for stream_mode.
        # Fall back to messages only — tools won't surface, but tokens still do.
        events = (
            ("messages", chunk) for chunk in agent.stream(payload, config, stream_mode="messages")
        )

    for mode, chunk in events:
        if mode == "messages":
            _handle_message_chunk(chunk, on_event)
        elif mode == "updates":
            _handle_node_update(chunk, on_event, streamed_call_ids, final_messages)

    return final_messages


def _handle_message_chunk(
    chunk: tuple[Any, dict[str, Any]],
    on_event: Callable[[dict[str, Any]], None],
) -> None:
    """Emit a `token` frame for each AIMessageChunk piece from the LLM."""
    try:
        message_chunk, metadata = chunk
    except (TypeError, ValueError):
        return

    # Only forward chunks from the agent node; the `tools` node also emits
    # message events for ToolMessages and we surface those via `updates`.
    node = (metadata or {}).get("langgraph_node")
    if node and node != "agent":
        return

    text = _chunk_text(message_chunk)
    if text:
        on_event({"type": "token", "content": text})


def _handle_node_update(
    update: dict[str, Any],
    on_event: Callable[[dict[str, Any]], None],
    streamed_call_ids: set[str],
    final_messages: list[Any],
) -> None:
    """Mine per-node updates for tool-call announcements + tool results."""
    if not isinstance(update, dict):
        return

    for node_name, node_state in update.items():
        if not isinstance(node_state, dict):
            continue
        messages = node_state.get("messages") or []
        for message in messages:
            if node_name == "agent":
                # The agent finished a step; harvest tool_calls so the user
                # sees what the model decided to invoke.
                for call in getattr(message, "tool_calls", None) or []:
                    cid = call.get("id") or ""
                    if cid and cid in streamed_call_ids:
                        continue
                    if cid:
                        streamed_call_ids.add(cid)
                    on_event(
                        {
                            "type": "tool_call",
                            "name": call.get("name", ""),
                            "args": _safe_args(call.get("args")),
                            "id": cid,
                        }
                    )
                final_messages.append(message)
            elif node_name == "tools":
                on_event(
                    {
                        "type": "tool_result",
                        "name": getattr(message, "name", "") or "",
                        "id": getattr(message, "tool_call_id", "") or "",
                        "content": _truncate(_message_content(message), 1200),
                    }
                )
                final_messages.append(message)


def _chunk_text(message_chunk: Any) -> str:
    """Extract a printable text fragment from an AIMessageChunk."""
    content = getattr(message_chunk, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out: list[str] = []
        for item in content:
            if isinstance(item, dict):
                # Gemini occasionally returns dict parts with `text` keys.
                piece = item.get("text") or item.get("content") or ""
                if piece:
                    out.append(str(piece))
            elif isinstance(item, str):
                out.append(item)
        return "".join(out)
    return ""


def _safe_args(args: Any) -> Any:
    """Make tool-call args JSON-safe for transport over WebSocket."""
    if args is None:
        return {}
    if isinstance(args, (str, int, float, bool, list, dict)):
        try:
            json.dumps(args)
            return args
        except TypeError:
            return str(args)
    return str(args)


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _compose_prompt(system_prompt: str, memory_text: str) -> str:
    prompt = system_prompt.strip()
    if memory_text:
        prompt += "\n\nRelevant memory context:\n" + memory_text
    prompt += (
        "\n\nUse tools only when they materially improve the answer. "
        "If a tool returns an error, explain the limitation and choose the next safest step."
    )
    return prompt


def _message_content(message: Any) -> str:
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("content") or item))
            else:
                parts.append(str(item))
        return "\n".join(parts)
    return str(content)
