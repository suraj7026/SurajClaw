"""Per-agent subgraph factory in WaqtAgent style.

Each registered SurajClaw agent (general, google_workspace, code_executor, notes,
plus runtime custom agents) compiles a `StateGraph(AgentState)` with two nodes:

    agent_llm  --  llm.bind_tools(tools).invoke([SystemMessage, *messages])
    tool_executor  --  ToolNode(tools)

Edges:

    entry            -> agent_llm
    agent_llm        -conditional-> tool_executor (when last AIMessage has tool_calls)
                     -conditional-> END           (otherwise, or loop cap reached)
    tool_executor    -> agent_llm  (loop)

This replaces the previous ``langgraph.prebuilt.create_react_agent`` shortcut
with explicit nodes the way ``Vyom_watches/WaqtAgent.py:Waqt`` does it. Each
node is a plain python function that mutates ``AgentState``; nothing magical
happens behind the scenes.

Tool-call activity is mirrored into ``state["tool_call_log"]`` and forwarded
to ``state["context"]["on_event"]`` (when set) so the WebSocket consumer keeps
receiving live ``tool_call`` / ``tool_result`` frames. We also drive the LLM
through ``bound.stream(...)`` and emit ``token`` frames as chunks arrive, so
the CLI / chat client can display assistant text incrementally.
"""
from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from agents.model_router import build_llm, route
from agents.state import AgentState

logger = logging.getLogger(__name__)


def _emit(state: AgentState, payload: dict[str, Any]) -> None:
    """Forward one frame to the consumer-supplied ``on_event`` callback."""
    on_event = (state.get("context") or {}).get("on_event")
    if not on_event:
        return
    try:
        on_event(payload)
    except Exception as exc:  # noqa: BLE001 -- streaming should not break the turn
        logger.debug("on_event callback failed: %s", exc)


def _message_text(message: Any) -> str:
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("content") or item))
            else:
                parts.append(str(item))
        return "\n".join(parts)
    return str(content)


def _chunk_text(chunk: AIMessageChunk) -> str:
    """Best-effort extraction of plain text from one streamed LLM chunk.

    LangChain chat-model chunks expose ``content`` as either ``str`` or a
    list of typed parts (``{"type": "text", "text": "..."}``,
    ``{"type": "tool_use", ...}``, ...). Tool-call parts have no human
    text and must not bleed into the live ``token`` stream.
    """
    content = getattr(chunk, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out: list[str] = []
        for part in content:
            if isinstance(part, str):
                out.append(part)
            elif isinstance(part, dict):
                ptype = part.get("type")
                if ptype in {"text", "output_text", None}:
                    text = part.get("text") or part.get("content")
                    if isinstance(text, str):
                        out.append(text)
        return "".join(out)
    return ""


def _stream_llm(bound: Any, composed: list[BaseMessage], state: AgentState, agent_id: str) -> AIMessage:
    """Stream an LLM response, emit ``token`` frames, return one ``AIMessage``.

    We rely on LangChain's ``BaseChatModel.stream`` contract: yields
    :class:`AIMessageChunk` instances that can be concatenated with ``+``
    to produce the final aggregate. If the model implementation falls
    back to non-streaming under the hood (some Gemini configs do this
    when tool calls are involved) we still get a single chunk and the
    behaviour is identical to the old ``invoke`` path.
    """
    aggregate: AIMessageChunk | None = None
    try:
        iterator = bound.stream(composed)
    except (TypeError, AttributeError):
        # The bound runnable does not support .stream(); fall back.
        result = bound.invoke(composed)
        if isinstance(result, AIMessage):
            return result
        return AIMessage(content=_message_text(result))

    for chunk in iterator:
        if not isinstance(chunk, AIMessageChunk):
            # Non-chunk yields shouldn't happen but be defensive.
            chunk = AIMessageChunk(content=_message_text(chunk))
        text = _chunk_text(chunk)
        if text:
            _emit(state, {"type": "token", "agent": agent_id, "content": text})
        aggregate = chunk if aggregate is None else aggregate + chunk

    if aggregate is None:
        return AIMessage(content="")
    # ``AIMessageChunk`` is a subclass of ``AIMessage``; downstream code
    # only cares about ``content`` and ``tool_calls`` which both share.
    return aggregate  # type: ignore[return-value]


def _ensure_human_message(messages: list[BaseMessage], user_message: str) -> list[BaseMessage]:
    if any(isinstance(m, HumanMessage) for m in messages):
        return messages
    return [HumanMessage(content=user_message), *messages]


def build_agent_subgraph(
    agent_id: str,
    system_prompt: str,
    tools: list[Any],
    *,
    max_loops: int = 8,
):
    """Compile and return a per-agent StateGraph (`agent_llm` + `tool_executor`)."""
    from langgraph.graph import END, StateGraph
    from langgraph.prebuilt import ToolNode

    tool_node = ToolNode(tools) if tools else None

    def agent_llm_node(state: AgentState) -> dict[str, Any]:
        prior = list(state.get("messages") or [])
        prior = _ensure_human_message(prior, state.get("user_message", ""))
        composed: list[BaseMessage] = [SystemMessage(content=system_prompt), *prior]

        choice = route(
            state.get("user_message", ""),
            requires_tools=bool(tools),
            session_id=state.get("session_id"),
            directive_model=(state.get("context") or {}).get("directives", {}).get("model"),
        )
        llm = build_llm(choice)
        bound = llm.bind_tools(tools) if tools else llm

        try:
            ai_msg = _stream_llm(bound, composed, state, agent_id)
        except Exception as exc:  # noqa: BLE001 -- surface the error as the assistant turn
            logger.exception("agent_llm invoke failed for %s", agent_id)
            err_text = f"[{agent_id} llm error: {exc}]"
            # Push the error to the live consumer too, so empty `final`
            # frames stop being the only signal of a broken specialist.
            _emit(state, {"type": "error", "agent": agent_id, "content": err_text})
            ai_msg = AIMessage(content=err_text)

        new_log: list[dict[str, Any]] = []
        for call in getattr(ai_msg, "tool_calls", None) or []:
            frame = {
                "type": "tool_call",
                "agent": agent_id,
                "name": call.get("name", ""),
                "args": call.get("args") or {},
                "id": call.get("id") or "",
            }
            new_log.append(frame)
            _emit(state, frame)

        return {
            "messages": [ai_msg],
            "tool_call_log": new_log,
            "loop_count": state.get("loop_count", 0) + 1,
            "model_used": choice.model,
        }

    def tool_executor_node(state: AgentState) -> dict[str, Any]:
        if tool_node is None:
            return {"messages": [], "tool_call_log": []}
        result = tool_node.invoke({"messages": state["messages"]})
        produced = result.get("messages", []) if isinstance(result, dict) else []
        new_log: list[dict[str, Any]] = []
        for tm in produced:
            if isinstance(tm, ToolMessage):
                frame = {
                    "type": "tool_result",
                    "agent": agent_id,
                    "name": getattr(tm, "name", "") or "",
                    "id": getattr(tm, "tool_call_id", "") or "",
                    "content": _message_text(tm)[:1200],
                }
                new_log.append(frame)
                _emit(state, frame)
        return {"messages": produced, "tool_call_log": new_log}

    def route_after_llm(state: AgentState) -> str:
        if state.get("loop_count", 0) >= max_loops:
            return "FINISH"
        msgs = state.get("messages") or []
        if not msgs:
            return "FINISH"
        last = msgs[-1]
        if isinstance(last, AIMessage) and getattr(last, "tool_calls", None):
            return "TOOL"
        return "FINISH"

    graph = StateGraph(AgentState)
    graph.add_node("agent_llm", agent_llm_node)
    if tool_node is not None:
        graph.add_node("tool_executor", tool_executor_node)
    graph.set_entry_point("agent_llm")
    if tool_node is not None:
        graph.add_conditional_edges(
            "agent_llm",
            route_after_llm,
            {"TOOL": "tool_executor", "FINISH": END},
        )
        graph.add_edge("tool_executor", "agent_llm")
    else:
        graph.add_edge("agent_llm", END)
    return graph.compile()


def last_ai_text(messages: list[BaseMessage]) -> str:
    """Return the text content of the most recent ``AIMessage`` in ``messages``."""
    for m in reversed(messages or []):
        if isinstance(m, AIMessage):
            return _message_text(m)
    return ""
