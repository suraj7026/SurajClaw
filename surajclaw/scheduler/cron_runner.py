"""CronJob runner: poll, fire, record, alert.

Adapted from OpenClaw's ``src/cron/service.ts`` and ``delivery.ts``. Wired
into Celery Beat as ``cron-job-poll`` (every 30s). The poller is idempotent
and uses ``select_for_update(skip_locked=True)`` so multiple workers don't
double-fire a job.

Schedule semantics:

* ``at`` — single fire. After running we set status=disabled.
* ``every`` — milliseconds between fires; next_run advances to ``last + interval``.
* ``cron`` — uses ``croniter`` (already a transitive dep via celery) to
  compute the next match. Falls back to a 1-hour interval if the expression
  can't be parsed; we emit a warning so it shows up in /doctor.
"""
from __future__ import annotations

import logging
import random
from datetime import datetime, timedelta, timezone

from celery import shared_task
from django.db import transaction
from django.utils import timezone as djtz

logger = logging.getLogger(__name__)


def _next_run_after(job, after: datetime) -> datetime | None:
    """Compute the next firing time for ``job`` strictly after ``after``."""
    from core.models import CronJob

    kind = job.schedule_kind
    val = job.schedule_value or ""
    base: datetime | None = None

    if kind == CronJob.ScheduleKind.AT:
        try:
            base = datetime.fromisoformat(val.replace("Z", "+00:00"))
        except ValueError:
            logger.warning("cron job %s has invalid 'at' value: %r", job.name, val)
            return None
        if base.tzinfo is None:
            base = base.replace(tzinfo=timezone.utc)
        return base if base > after else None

    if kind == CronJob.ScheduleKind.EVERY:
        try:
            interval_ms = int(val)
        except ValueError:
            logger.warning("cron job %s has invalid 'every' value: %r", job.name, val)
            return None
        base = after + timedelta(milliseconds=interval_ms)
    elif kind == CronJob.ScheduleKind.CRON:
        try:
            from croniter import croniter
        except ImportError:
            logger.warning("croniter not installed; cron job %s falls back to 1h", job.name)
            base = after + timedelta(hours=1)
        else:
            try:
                base = croniter(val, after).get_next(datetime)
                if base.tzinfo is None:
                    base = base.replace(tzinfo=timezone.utc)
            except (ValueError, KeyError) as exc:
                logger.warning("cron job %s has bad cron expr %r: %s", job.name, val, exc)
                base = after + timedelta(hours=1)
    else:
        return None

    if job.stagger_seconds:
        # Deterministic-ish jitter: same job picks same offset within window.
        rng = random.Random(str(job.id))
        base = base + timedelta(seconds=rng.uniform(0, job.stagger_seconds))
    return base


def _record_run(job, *, status, summary="", error_text="", started_at, finished_at) -> None:
    from core.models import CronRun

    CronRun.objects.create(
        job=job,
        status=status,
        started_at=started_at,
        finished_at=finished_at,
        duration_ms=int((finished_at - started_at).total_seconds() * 1000),
        summary=summary[:4000],
        error_text=error_text[:4000],
    )


def _maybe_alert_failure(job) -> None:
    """Send a failure alert if past the threshold and out of cooldown."""
    if job.consecutive_failures < job.fail_alert_after:
        return
    now = djtz.now()
    cooldown = timedelta(seconds=job.fail_alert_cooldown_seconds)
    if job.last_failure_alert_at and now - job.last_failure_alert_at < cooldown:
        return
    logger.error(
        "cron job %s has failed %d consecutive times — would alert here",
        job.name,
        job.consecutive_failures,
    )
    # TODO: dispatch via channel based on job.delivery_*; for now we log.
    job.last_failure_alert_at = now
    job.save(update_fields=["last_failure_alert_at"])


def _execute(job) -> tuple[str, str, str]:
    """Run the job's prompt. Returns (status, summary, error_text)."""
    if not job.prompt:
        return "ok", "no-op (empty prompt)", ""
    try:
        from agents.graph import run_turn

        # Cron runs use a synthetic session id so messages are grouped.
        session_id = f"cron:{job.id}"
        text = run_turn(session_id=session_id, message=job.prompt, source="cron")
        return "ok", (text or "")[:4000], ""
    except Exception as exc:  # noqa: BLE001 -- job failures are recoverable
        logger.exception("cron job %s execution failed", job.name)
        return "error", "", str(exc)


@shared_task
def cron_job_poll() -> int:
    """Poll due CronJobs and fire them. Returns the number of jobs fired."""
    from core.models import CronJob

    now = djtz.now()
    fired = 0

    # SELECT FOR UPDATE SKIP LOCKED so two workers polling concurrently
    # don't claim the same job. This is the same idempotency trick OpenClaw
    # uses in cron/service.ts via its in-process arm-timer guard.
    with transaction.atomic():
        due = (
            CronJob.objects.select_for_update(skip_locked=True)
            .filter(
                status=CronJob.Status.ACTIVE,
                next_run_at__lte=now,
                running_since__isnull=True,
            )
            .order_by("next_run_at")[:25]
        )
        claimed = list(due)
        for job in claimed:
            job.running_since = now
            job.save(update_fields=["running_since"])

    for job in claimed:
        started = djtz.now()
        status, summary, err = _execute(job)
        finished = djtz.now()
        _record_run(
            job,
            status=status,
            summary=summary,
            error_text=err,
            started_at=started,
            finished_at=finished,
        )

        if status == "ok":
            job.consecutive_failures = 0
        else:
            job.consecutive_failures += 1

        next_run = _next_run_after(job, finished)
        job.last_run_at = finished
        job.last_run_status = status
        job.running_since = None
        if job.schedule_kind == CronJob.ScheduleKind.AT:
            # one-shot
            job.status = CronJob.Status.DISABLED
            job.next_run_at = None
        else:
            job.next_run_at = next_run
        job.save(
            update_fields=[
                "consecutive_failures",
                "last_run_at",
                "last_run_status",
                "running_since",
                "status",
                "next_run_at",
            ]
        )

        if status == "error":
            _maybe_alert_failure(job)
        fired += 1

    return fired
