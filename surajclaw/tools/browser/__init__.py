"""Browser-agent helper tools.

Today this module only exposes ``browser.confirm_purchase`` -- a no-op tool
that exists purely so the Browser Agent can hit the approval gate before
submitting a checkout / payment form. Real navigation happens via the
Playwright MCP tools registered under ``mcp.playwright.*``.
"""
from __future__ import annotations

from agents.types import ToolDefinition
from tools.registry import register_tool


def confirm_purchase(url: str, summary: str, total: str = "") -> dict[str, object]:
    """Acknowledge a checkout/payment step. Gated by approval/gate.GATED_TOOLS."""
    detail = summary
    if total:
        detail += f" (total: {total})"
    return {
        "ok": True,
        "output": f"Purchase approved by operator: {detail} at {url}",
        "structured": {"url": url, "summary": summary, "total": total},
    }


register_tool(
    ToolDefinition(
        id="browser.confirm_purchase",
        callable=confirm_purchase,
        description=(
            "MUST be called before submitting any checkout / payment / booking "
            "form. Pauses for explicit operator approval. Args: url (the page "
            "you're about to submit), summary (one-line description of the "
            "purchase), total (the displayed total, optional)."
        ),
        approval_required=True,
        risk_level="high",
    )
)
