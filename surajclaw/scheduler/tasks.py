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


# ---------------------------------------------------------------------------
# Agent dispatch
# ---------------------------------------------------------------------------
@shared_task
def run_agent_turn(session_id: str, message: str, source: str = "web") -> None:
    """Execute one agent turn for an inbound user message.

    Wires up input → LangGraph → channel-layer streaming back to the WS.
    The concrete implementation is added as part of the agents module.
    """
    from agents.graph import run_turn  # local import: heavy LangGraph deps

    run_turn(session_id=session_id, message=message, source=source)


# ---------------------------------------------------------------------------
# Webhook dispatch (kept async so webhook handlers return 200 fast)
# ---------------------------------------------------------------------------
@shared_task
def handle_telegram_update(update: dict[str, Any]) -> None:
    logger.info("telegram update received: %s", update.get("update_id"))


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
