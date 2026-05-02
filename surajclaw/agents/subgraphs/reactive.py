"""Shared LLM + tool ReAct runner for SurajClaw agents."""
from __future__ import annotations

from typing import Any

from agents.model_router import build_llm, route
from agents.state import AgentState


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
    directives = (state.get("context") or {}).get("directives") or {}
    choice = route(
        task,
        requires_tools=bool(tools),
        complexity_hint=str(directives.get("thinking") or ""),
        session_id=state.get("session_id"),
        directive_model=directives.get("model"),
    )
    llm = build_llm(choice)
    memory_text = format_context((state.get("context") or {}).get("memory_context") or {})
    prompt = _compose_prompt(system_prompt, memory_text)
    agent = create_react_agent(llm, tools, prompt=prompt)
    result = agent.invoke(
        {"messages": [HumanMessage(content=task)]},
        {"recursion_limit": max(8, state.get("max_steps", 6) * 4)},
    )
    messages = result.get("messages", [])
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
