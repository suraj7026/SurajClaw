"""Tool: ``google.accounts.list`` -- enumerate connected Google accounts.

Used by the Workspace agent's recipes when it needs to know which labels
exist before issuing per-account write calls.
"""
from __future__ import annotations

from typing import Any

from agents.types import ToolDefinition
from core.google_accounts import list_accounts
from tools.registry import register_tool


def list_google_accounts() -> dict[str, Any]:
    accounts = list_accounts()
    items = [
        {"label": a.label, "token_path": str(a.token_path)} for a in accounts
    ]
    return {
        "ok": True,
        "output": (
            ", ".join(a["label"] for a in items)
            if items
            else "no Google accounts connected"
        ),
        "structured": {"accounts": items},
    }


def register() -> None:
    register_tool(ToolDefinition(
        id="google.accounts.list",
        callable=list_google_accounts,
        description=(
            "List labels of all connected Google accounts. Call this when you "
            "don't already know which account labels exist."
        ),
    ))
