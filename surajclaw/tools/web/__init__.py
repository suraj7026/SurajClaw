"""Web search tools."""
from __future__ import annotations

from django.conf import settings

from agents.types import ToolDefinition
from tools.registry import register_tool


def web_search(query: str, limit: int = 5) -> dict:
    if not settings.GOOGLE_SEARCH_API_KEY or not settings.GOOGLE_SEARCH_CX:
        return {
            "ok": False,
            "output": "GOOGLE_SEARCH_API_KEY and GOOGLE_SEARCH_CX are required for web search.",
            "error": "missing_env",
        }

    import httpx

    response = httpx.get(
        "https://www.googleapis.com/customsearch/v1",
        params={
            "key": settings.GOOGLE_SEARCH_API_KEY,
            "cx": settings.GOOGLE_SEARCH_CX,
            "q": query,
            "num": max(1, min(limit, 10)),
        },
        timeout=15.0,
    )
    response.raise_for_status()
    items = response.json().get("items", [])
    lines = [
        f"{item.get('title', 'Untitled')} - {item.get('link', '')}\n{item.get('snippet', '')}"
        for item in items
    ]
    return {"ok": True, "output": "\n\n".join(lines) or "No results.", "structured": {"items": items}}


register_tool(
    ToolDefinition(
        "web.search",
        web_search,
        "Search the web with Google Custom Search.",
    )
)
