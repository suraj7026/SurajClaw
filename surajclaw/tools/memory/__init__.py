"""Memory retrieval tools."""
from __future__ import annotations

from agents.types import ToolDefinition
from tools.registry import register_tool


def memory_search(query: str, limit: int = 5) -> dict:
    from memory.services import context_loader, format_context

    context = context_loader(query, limit_per_source=max(1, min(limit, 10)))
    output = format_context(context) or "No relevant memory found."
    return {"ok": True, "output": output, "structured": context}


register_tool(ToolDefinition("memory.search", memory_search, "Search notes, session summaries, and entities."))
