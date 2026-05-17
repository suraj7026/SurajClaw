"""``surajclaw mcp-serve`` -- expose SurajClaw as an MCP server.

Lets external MCP clients (Claude Code, Cursor, ChatGPT desktop, ...) reach
into SurajClaw to read conversations, send messages, queue Kanban tasks,
respond to pending approvals, and search memory.

Inspired by hermes-agent's ``mcp_serve.py``.

Run it as a Django management script so the ORM is fully wired::

    python manage.py mcp_serve

The transport is stdio so the parent client owns the lifecycle. To run as
an SSE/HTTP server inside the Daphne process is a follow-up (would need a
streamable_http endpoint mounted at /mcp).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from typing import Any

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
django.setup()


logger = logging.getLogger("surajclaw.mcp_server")


def _tool_conversations_list(limit: int = 20) -> dict[str, Any]:
    """Recent chat sessions and their last-active timestamps."""
    from core.models import Session

    rows = Session.objects.order_by("-updated_at")[: max(1, min(limit, 100))]
    return {
        "conversations": [
            {
                "session_id": str(s.id),
                "source": s.source,
                "is_active": s.is_active,
                "created_at": s.created_at.isoformat(),
                "updated_at": s.updated_at.isoformat(),
            }
            for s in rows
        ]
    }


def _tool_messages_read(session_id: str, limit: int = 50) -> dict[str, Any]:
    """Read recent messages for one session, oldest first."""
    from core.models import Message

    rows = (
        Message.objects.filter(session_id=session_id)
        .order_by("-created_at")[: max(1, min(limit, 200))]
    )
    rows = list(reversed(list(rows)))
    return {
        "session_id": session_id,
        "messages": [
            {
                "role": m.role,
                "content": m.content,
                "model_used": m.model_used,
                "created_at": m.created_at.isoformat(),
            }
            for m in rows
        ],
    }


def _tool_send_telegram(chat_id: str, text: str) -> dict[str, Any]:
    """Send a message via the Telegram bot (uses ``TELEGRAM_BOT_TOKEN``)."""
    from django.conf import settings
    import httpx

    token = getattr(settings, "TELEGRAM_BOT_TOKEN", "")
    if not token:
        return {"ok": False, "error": "TELEGRAM_BOT_TOKEN not configured"}
    r = httpx.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text[:4000]},
        timeout=10,
    )
    r.raise_for_status()
    return {"ok": True, "telegram_response": r.json()}


def _tool_pending_approvals() -> dict[str, Any]:
    """List approval requests waiting for a decision."""
    from approval.models import ApprovalRequest
    from django.utils import timezone

    rows = ApprovalRequest.objects.filter(
        status=ApprovalRequest.Status.PENDING,
        expires_at__gt=timezone.now(),
    ).order_by("-created_at")[:50]
    return {
        "approvals": [
            {
                "id": str(r.id),
                "tool_id": r.tool_id,
                "description": r.description,
                "session_id": str(r.session_id),
                "created_at": r.created_at.isoformat(),
                "expires_at": r.expires_at.isoformat(),
            }
            for r in rows
        ]
    }


def _tool_respond_approval(request_id: str, approve: bool, by: str = "mcp") -> dict[str, Any]:
    from approval.models import ApprovalRequest
    from django.utils import timezone

    try:
        ar = ApprovalRequest.objects.get(pk=request_id)
    except ApprovalRequest.DoesNotExist:
        return {"ok": False, "error": "not found"}
    if ar.status != ApprovalRequest.Status.PENDING:
        return {"ok": False, "error": f"already {ar.status}"}
    ar.status = (
        ApprovalRequest.Status.APPROVED if approve else ApprovalRequest.Status.REJECTED
    )
    ar.responded_by = by[:128]
    ar.responded_at = timezone.now()
    ar.save(update_fields=["status", "responded_by", "responded_at"])
    return {"ok": True, "status": ar.status}


def _tool_memory_search(query: str, k: int = 5) -> dict[str, Any]:
    """Semantic search over notes / entities (uses pgvector under the hood)."""
    try:
        from tools.memory import memory_search  # registered tool callable
    except Exception as exc:
        return {"ok": False, "error": f"memory tool unavailable: {exc}"}
    try:
        result = memory_search(query=query, k=max(1, min(k, 20)))
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}
    return result if isinstance(result, dict) else {"result": str(result)}


def _tool_kanban_enqueue(
    title: str,
    prompt: str,
    agent_id: str = "",
    model_provider: str = "",
    priority: int = 0,
) -> dict[str, Any]:
    """Drop a long-running task onto the durable Kanban queue."""
    from kanban.services import enqueue

    task = enqueue(
        title=title,
        prompt=prompt,
        agent_id=agent_id,
        model_provider=model_provider,
        priority=priority,
        created_by="mcp",
    )
    return {"ok": True, "task_id": str(task.id), "status": task.status}


def _tool_kanban_status(task_id: str) -> dict[str, Any]:
    from kanban.models import KanbanTask

    try:
        t = KanbanTask.objects.get(pk=task_id)
    except KanbanTask.DoesNotExist:
        return {"ok": False, "error": "not found"}
    return {
        "ok": True,
        "task_id": str(t.id),
        "status": t.status,
        "attempts": t.attempts,
        "result": t.result,
        "error_text": t.error_text,
    }


# ---------------------------------------------------------------------------
# MCP server registration (uses the official Python SDK).
# ---------------------------------------------------------------------------
def _build_server():
    try:
        from mcp.server import FastMCP
    except ImportError as exc:
        raise SystemExit(
            "mcp package not installed. Run: pip install mcp"
        ) from exc

    server = FastMCP("surajclaw")

    @server.tool()
    def conversations_list(limit: int = 20) -> dict:
        """List recent SurajClaw sessions with last-active timestamps."""
        return _tool_conversations_list(limit)

    @server.tool()
    def messages_read(session_id: str, limit: int = 50) -> dict:
        """Return the most recent messages of one session, oldest first."""
        return _tool_messages_read(session_id, limit)

    @server.tool()
    def send_telegram(chat_id: str, text: str) -> dict:
        """Send a text message via the configured Telegram bot."""
        return _tool_send_telegram(chat_id, text)

    @server.tool()
    def pending_approvals() -> dict:
        """List approval requests still waiting on the operator."""
        return _tool_pending_approvals()

    @server.tool()
    def respond_to_approval(request_id: str, approve: bool, by: str = "mcp") -> dict:
        """Approve or reject a pending approval request by id."""
        return _tool_respond_approval(request_id, approve, by)

    @server.tool()
    def memory_search(query: str, k: int = 5) -> dict:
        """Semantic search across notes + entities."""
        return _tool_memory_search(query, k)

    @server.tool()
    def kanban_enqueue(
        title: str,
        prompt: str,
        agent_id: str = "",
        model_provider: str = "",
        priority: int = 0,
    ) -> dict:
        """Queue a long-running agent task on the durable Kanban board."""
        return _tool_kanban_enqueue(title, prompt, agent_id, model_provider, priority)

    @server.tool()
    def kanban_status(task_id: str) -> dict:
        """Check the status (and result, if done) of a Kanban task."""
        return _tool_kanban_status(task_id)

    return server


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    server = _build_server()
    # FastMCP's .run() defaults to stdio. To run over SSE, pass transport="sse".
    server.run()


if __name__ == "__main__":
    main()
