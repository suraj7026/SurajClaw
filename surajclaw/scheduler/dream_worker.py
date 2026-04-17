"""Dream consolidation daemon.

Runs as a Celery periodic task every 30 minutes. Checks trigger conditions
(N sessions since last dream AND M hours elapsed); when both are met,
acquires the singleton dream lock and invokes the LangGraph `dream_node`.

The dream node runs with a sandboxed context: read-only access to sessions
and raw memory, write access only to notes/ and the entities table.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task
def dream_check() -> None:
    from core.models import SystemState

    last_dream_raw = SystemState.get("last_dream_at")
    last_count_raw = SystemState.get("last_dream_session_count", "0")

    # Count sessions since last dream. Deferred import so this file is
    # importable before phase-1 migrations are applied.
    from core.models import Session

    now = timezone.now()
    last_dream_at = None
    if last_dream_raw:
        try:
            last_dream_at = timezone.datetime.fromisoformat(last_dream_raw)
        except ValueError:
            last_dream_at = None

    if last_dream_at is not None:
        hours_since = (now - last_dream_at).total_seconds() / 3600.0
    else:
        hours_since = 1e9  # first dream ever

    if last_dream_at is not None:
        new_sessions = Session.objects.filter(started_at__gte=last_dream_at).count()
    else:
        new_sessions = Session.objects.count()

    min_sessions = settings.DREAM_MIN_SESSIONS
    min_hours = settings.DREAM_MIN_HOURS

    if new_sessions < min_sessions or hours_since < min_hours:
        logger.debug(
            "dream_check: skip (sessions=%d/%d, hours=%.2f/%d)",
            new_sessions, min_sessions, hours_since, min_hours,
        )
        return

    logger.info(
        "dream_check: TRIGGER (sessions=%d, hours=%.2f) — running consolidation",
        new_sessions, hours_since,
    )
    run_dream.delay(trigger="auto", sessions_processed=new_sessions)


@shared_task
def run_dream(trigger: str = "manual", sessions_processed: int = 0) -> None:
    """Actually perform the dream consolidation.

    Held-lock semantics are enforced by SystemState key `dream_lock`; only one
    dream runs at a time across the whole deployment.
    """
    from core.models import SystemState

    lock_value = SystemState.get("dream_lock")
    if lock_value == "locked":
        logger.warning("run_dream: lock held, skipping")
        return

    SystemState.set("dream_lock", "locked")
    try:
        # Agents module loaded lazily so missing LangGraph during early-phase
        # deployments does not break Celery startup.
        from agents.nodes.dream import consolidate

        result = consolidate(trigger=trigger, sessions_processed=sessions_processed)

        SystemState.set("last_dream_at", timezone.now().isoformat())
        SystemState.set("last_dream_session_count", str(sessions_processed))
        logger.info("run_dream: done: %s", result)
    finally:
        SystemState.set("dream_lock", "unlocked")
