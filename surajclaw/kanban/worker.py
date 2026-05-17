"""Kanban dispatcher and stale-claim reaper.

Wired into Celery Beat in ``config/celery.py``:

* ``kanban_dispatch`` (every 30s): atomically claim N queued tasks per tick,
  run each through ``agents.invocation.invoke_agent`` (or ``agents.graph.run_turn``
  for the GENERAL agent), heartbeating periodically.
* ``kanban_reclaim_stale`` (every 5min): reset CLAIMED rows whose heartbeat
  is older than ``stale_after_seconds`` back to QUEUED. Hermes calls this a
  zombie sweep.

Worker survival: tasks live in Postgres so a Daphne / Celery restart loses
nothing -- the next dispatch tick picks the row up again.
"""
from __future__ import annotations

import logging
import socket
import time
import uuid
from datetime import timedelta

from celery import shared_task
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


WORKER_ID = f"{socket.gethostname()}:{uuid.uuid4().hex[:8]}"
DISPATCH_BATCH = 2
HEARTBEAT_INTERVAL_SECONDS = 30


def _claim_next() -> list:
    """Claim up to DISPATCH_BATCH queued tasks atomically. Returns the rows."""
    from kanban.models import KanbanTask

    now = timezone.now()
    claimed = []
    with transaction.atomic():
        rows = (
            KanbanTask.objects.select_for_update(skip_locked=True)
            .filter(status=KanbanTask.Status.QUEUED)
            .order_by("-priority", "created_at")[:DISPATCH_BATCH]
        )
        for task in rows:
            task.status = KanbanTask.Status.CLAIMED
            task.claim_id = WORKER_ID
            task.claimed_at = now
            task.heartbeat_at = now
            task.attempts += 1
            task.save(
                update_fields=[
                    "status",
                    "claim_id",
                    "claimed_at",
                    "heartbeat_at",
                    "attempts",
                ]
            )
            claimed.append(task)
    return claimed


def _run_one(task) -> None:
    """Execute one claimed task. Updates row to DONE / FAILED."""
    from kanban.models import KanbanTask

    started = timezone.now()
    task.status = KanbanTask.Status.RUNNING
    task.started_at = started
    task.heartbeat_at = started
    task.save(update_fields=["status", "started_at", "heartbeat_at"])

    try:
        result = _invoke_agent_for(task)
        task.status = KanbanTask.Status.DONE
        task.result = (result or "")[:8000]
        task.error_text = ""
    except Exception as exc:  # noqa: BLE001
        logger.exception("kanban task %s failed", task.id)
        if task.attempts >= task.max_attempts:
            task.status = KanbanTask.Status.FAILED
            task.error_text = str(exc)[:4000]
        else:
            task.status = KanbanTask.Status.QUEUED
            task.claim_id = ""
            task.claimed_at = None
            task.heartbeat_at = None
            task.error_text = f"retry after error: {exc}"[:4000]
    finally:
        task.finished_at = timezone.now()
        task.save(
            update_fields=[
                "status",
                "result",
                "error_text",
                "finished_at",
                "claim_id",
                "claimed_at",
                "heartbeat_at",
            ]
        )


def _invoke_agent_for(task) -> str:
    """Run the agent associated with this task. Returns the response text."""
    directives = {}
    if (task.model_provider or "").strip():
        directives["model"] = task.model_provider.strip()
    if (task.agent_id or "").strip():
        directives["agent"] = task.agent_id.strip()

    from agents.graph import run_turn

    session_id = f"kanban:{task.id}"
    return run_turn(
        session_id=session_id,
        message=task.prompt,
        source="kanban",
        directives=directives or None,
    )


def _heartbeat(task) -> None:
    from kanban.models import KanbanTask

    KanbanTask.objects.filter(id=task.id).update(heartbeat_at=timezone.now())


@shared_task
def kanban_dispatch() -> int:
    """Beat-driven entry point: claim and run up to DISPATCH_BATCH tasks."""
    claimed = _claim_next()
    for task in claimed:
        # Heartbeat once before the agent call so the reaper sees a fresh ts
        # even if the LLM call takes most of a stale-after window.
        _heartbeat(task)
        try:
            _run_one(task)
        except Exception as exc:  # noqa: BLE001
            logger.exception("kanban dispatcher: failure on %s: %s", task.id, exc)
    return len(claimed)


@shared_task
def kanban_reclaim_stale() -> int:
    """Reset CLAIMED tasks whose heartbeat is older than stale_after_seconds."""
    from kanban.models import KanbanTask

    now = timezone.now()
    reset = 0
    # Iterate one-by-one because stale_after_seconds is per-row.
    candidates = KanbanTask.objects.filter(
        status__in=[KanbanTask.Status.CLAIMED, KanbanTask.Status.RUNNING],
        heartbeat_at__isnull=False,
    ).only("id", "heartbeat_at", "stale_after_seconds")
    for task in candidates:
        cutoff = now - timedelta(seconds=task.stale_after_seconds)
        if task.heartbeat_at < cutoff:
            updated = KanbanTask.objects.filter(
                id=task.id,
                status__in=[KanbanTask.Status.CLAIMED, KanbanTask.Status.RUNNING],
            ).update(
                status=KanbanTask.Status.QUEUED,
                claim_id="",
                claimed_at=None,
                heartbeat_at=None,
                error_text="reclaimed: stale claim",
            )
            reset += updated
    return reset
