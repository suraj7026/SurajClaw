"""Celery tasks for scheduled jobs and async dispatches.

Each task is intentionally a thin wrapper: it resolves the right service or
agent entrypoint and calls it. Keeping tasks thin makes them easy to test
synchronously and keeps orchestration logic in one place (agents/, tools/).
"""
from __future__ import annotations

import logging
from typing import Any

from celery import shared_task

logger = logging.getLogger(__name__)

# Celery's autodiscover_tasks() only imports `scheduler.tasks`. Side-import the
# sibling task modules here so their @shared_task decorators register on the
# worker (otherwise beat fires e.g. `cron_job_poll` and the worker rejects it
# as "Received unregistered task of type ...").
from scheduler import (  # noqa: E402, F401
    cron_runner,
    dream_worker,
    email_poller,
    gmail_watch,
)
from kanban import worker as _kanban_worker  # noqa: E402, F401


# ---------------------------------------------------------------------------
# Agent dispatch
# ---------------------------------------------------------------------------
@shared_task
def run_agent_turn(
    session_id: str,
    message: str,
    source: str = "web",
    directives: dict[str, Any] | None = None,
) -> None:
    """Execute one agent turn for an inbound user message.

    ``directives`` carries per-turn overrides parsed from inline ``!key value``
    syntax (model pin, thinking budget, tool allow-list). They flow through to
    the model router via ``run_turn``.
    """
    from agents.graph import run_turn  # local import: heavy LangGraph deps

    run_turn(
        session_id=session_id,
        message=message,
        source=source,
        directives=directives or {},
    )


# ---------------------------------------------------------------------------
# Webhook dispatch (kept async so webhook handlers return 200 fast)
# ---------------------------------------------------------------------------
@shared_task
def handle_telegram_update(
    update: dict[str, Any],
    sender_id: str | None = None,
    chat_id: str | None = None,
    text: str = "",
) -> None:
    """Run the telegram message through the same command pipeline as web chat."""
    from chat.auth import is_owner
    from chat.commands import (
        CommandContext,
        detect as detect_command,
        dispatch as dispatch_command,
    )
    from chat.directives import parse as parse_directives

    logger.info("telegram update received: %s", update.get("update_id"))
    if not text or not chat_id:
        return

    session_id = f"telegram:{chat_id}"
    is_authorized = is_owner("telegram", sender_id)

    match = detect_command(text)
    if match is not None:
        ctx = CommandContext(
            session_id=session_id,
            sender_id=sender_id,
            channel="telegram",
            args=match.args,
            is_owner=is_authorized,
        )
        result = dispatch_command(match, ctx)
        _telegram_send(chat_id, result.text)
        return

    directives, body = parse_directives(text)
    if not body:
        return
    run_agent_turn.delay(
        session_id=session_id,
        message=body,
        source="telegram",
        directives={
            "model": directives.model,
            "thinking": directives.thinking,
            "tools_allow": directives.tools_allow,
        },
    )


def _telegram_send(chat_id: str, text: str) -> None:
    """Best-effort sendMessage to Telegram. Logs and swallows failures."""
    from django.conf import settings

    token = settings.TELEGRAM_BOT_TOKEN
    if not token or not text:
        return
    try:
        import urllib.parse
        import urllib.request

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode()
        req = urllib.request.Request(url, data=data, method="POST")
        urllib.request.urlopen(req, timeout=5).read()  # noqa: S310 -- official API
    except Exception as exc:  # noqa: BLE001
        logger.warning("telegram sendMessage failed: %s", exc)


@shared_task
def handle_github_event(event_type: str, payload: dict[str, Any]) -> None:
    logger.info("github event=%s action=%s", event_type, payload.get("action"))


@shared_task
def handle_gmail_push(data: dict[str, Any]) -> None:
    logger.info("gmail push: %s", data.get("historyId"))


# ---------------------------------------------------------------------------
# Scheduled jobs (wired in config/celery.py beat_schedule)
# ---------------------------------------------------------------------------
@shared_task
def daily_briefing() -> None:
    """08:00 weekdays. Calendar + tasks + inbox + RSS summary → Telegram."""
    logger.info("daily_briefing: run")


@shared_task
def rss_poll() -> None:
    """Every 30 min. Poll active RSS feeds, persist new items."""
    logger.info("rss_poll: run")


@shared_task
def future_queue_poll() -> None:
    """Every minute. Fire any FutureQueue items whose due_at has passed."""
    logger.info("future_queue_poll: run")


@shared_task
def db_backup() -> None:
    """Daily 03:00. Run pg_dump into the backups directory."""
    logger.info("db_backup: run")


@shared_task
def index_session_embedding(session_id: str) -> None:
    """Upsert a SessionEmbedding row for ``session_id``.

    Called from ``agents.graph.run_turn`` right after the assistant message
    is persisted, so semantic recall (memory.search → semantic_search_sessions)
    sees the conversation as soon as the next turn begins — not after the
    ``dream_check`` batch window. Best-effort: any failure is logged and
    swallowed so it cannot retroactively break the user's turn.
    """
    from django.db import transaction

    from core.models import Message, Session
    from memory.models import SessionEmbedding
    from memory.services import embed_text

    try:
        session = Session.objects.get(id=session_id)
    except Session.DoesNotExist:
        logger.debug("index_session_embedding: session %s not found", session_id)
        return

    messages = list(
        Message.objects.filter(
            session_id=session_id,
            role__in=[Message.Role.USER, Message.Role.ASSISTANT],
        )
        .order_by("-created_at")
        .only("role", "content")[:20]
    )[::-1]
    if not messages:
        return

    parts: list[str] = []
    for m in messages:
        speaker = "User" if m.role == Message.Role.USER else "Assistant"
        parts.append(f"{speaker}: {m.content or ''}")
    summary = "\n\n".join(parts)
    if len(summary) > 6000:
        summary = summary[-6000:]  # tail-bias to most recent context

    try:
        vec = embed_text(summary)
    except Exception as exc:  # noqa: BLE001
        logger.warning("index_session_embedding: embed_text failed: %s", exc)
        return

    with transaction.atomic():
        SessionEmbedding.objects.update_or_create(
            session=session,
            defaults={"summary_text": summary, "embedding": vec},
        )


@shared_task
def approval_expire() -> None:
    """Every minute. Mark any ApprovalRequest past expires_at as expired."""
    from django.utils import timezone

    try:
        from approval.models import ApprovalRequest
    except ImportError:
        # Migration not yet applied.
        return

    now = timezone.now()
    ApprovalRequest.objects.filter(
        status=ApprovalRequest.Status.PENDING,
        expires_at__lt=now,
    ).update(status=ApprovalRequest.Status.EXPIRED)
