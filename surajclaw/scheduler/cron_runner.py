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


def _record_run(
    job,
    *,
    status,
    summary="",
    error_text="",
    started_at,
    finished_at,
    delivery_status="",
) -> None:
    from core.models import CronRun

    CronRun.objects.create(
        job=job,
        status=status,
        started_at=started_at,
        finished_at=finished_at,
        duration_ms=int((finished_at - started_at).total_seconds() * 1000),
        summary=summary[:4000],
        error_text=error_text[:4000],
        delivery_status=delivery_status[:16],
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
        directives: dict = {}
        if (job.model_provider or "").strip():
            directives["model"] = job.model_provider.strip()
        text = run_turn(
            session_id=session_id,
            message=job.prompt,
            source="cron",
            directives=directives or None,
        )
        captured = (text or "")[:4000] if job.capture_output else ""
        return "ok", captured, ""
    except Exception as exc:  # noqa: BLE001 -- job failures are recoverable
        logger.exception("cron job %s execution failed", job.name)
        return "error", "", str(exc)


def _deliver(job, status: str, summary: str, error_text: str) -> str:
    """Fan out the run result to every configured delivery target.

    Returns a short status tag for CronRun.delivery_status:
        "delivered"      -- at least one target succeeded
        "not-delivered"  -- every target raised
        "not-requested"  -- nothing configured
    """
    targets: list[dict] = list(job.delivery_targets or [])
    if not targets and job.delivery_mode != "none":
        # Back-compat: single-target spec still supported.
        if job.delivery_mode == "webhook" and job.delivery_webhook_url:
            targets.append({"channel": "webhook", "url": job.delivery_webhook_url})
        elif job.delivery_mode == "announce" and job.delivery_channel:
            targets.append({"channel": job.delivery_channel, "to": job.delivery_to})
    if not targets:
        return "not-requested"

    payload_text = summary or error_text or f"cron {job.name}: {status}"
    ok_count = 0
    err_count = 0
    for tgt in targets:
        ch = (tgt.get("channel") or "").lower()
        try:
            if ch == "log":
                logger.info("cron[%s] -> %s", job.name, payload_text[:400])
            elif ch == "webhook":
                _deliver_webhook(tgt.get("url", ""), job, status, payload_text)
            elif ch == "telegram":
                _deliver_telegram(tgt.get("to", ""), payload_text)
            elif ch == "email":
                _deliver_email(tgt.get("to", ""), f"cron[{job.name}] {status}", payload_text)
            else:
                logger.warning("cron[%s]: unknown delivery channel %r", job.name, ch)
                err_count += 1
                continue
            ok_count += 1
        except Exception as exc:  # noqa: BLE001 -- per-target isolation
            logger.warning("cron[%s] delivery to %s failed: %s", job.name, ch, exc)
            err_count += 1

    if ok_count and not err_count:
        return "delivered"
    if ok_count:
        return "delivered-partial"
    return "not-delivered"


def _deliver_webhook(url: str, job, status: str, body: str) -> None:
    if not url:
        raise ValueError("webhook delivery missing url")
    import httpx

    httpx.post(
        url,
        json={
            "job_id": str(job.id),
            "job_name": job.name,
            "status": status,
            "summary": body,
        },
        timeout=10,
    ).raise_for_status()


def _deliver_telegram(chat_id: str, text: str) -> None:
    if not chat_id:
        raise ValueError("telegram delivery missing 'to' (chat_id)")
    from django.conf import settings
    import httpx

    token = getattr(settings, "TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not configured")
    httpx.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text[:4000]},
        timeout=10,
    ).raise_for_status()


def _deliver_email(to: str, subject: str, body: str) -> None:
    if not to:
        raise ValueError("email delivery missing 'to'")
    from django.core.mail import EmailMessage

    EmailMessage(subject=subject[:200], body=body, to=[to]).send(fail_silently=False)


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
        delivery_status = _deliver(job, status, summary, err)
        finished = djtz.now()
        _record_run(
            job,
            status=status,
            summary=summary,
            error_text=err,
            started_at=started,
            finished_at=finished,
            delivery_status=delivery_status,
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
