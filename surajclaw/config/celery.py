"""Celery application for SurajClaw background tasks.

Schedule is defined below (Celery Beat). Tasks live in `scheduler/tasks.py`
and `scheduler/dream_worker.py`.
"""
from __future__ import annotations

import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

app = Celery("surajclaw")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

# ---------------------------------------------------------------------------
# Beat schedule
# ---------------------------------------------------------------------------
# Note: schedules are also representable via django_celery_beat's DB scheduler
# (CELERY_BEAT_SCHEDULER in settings). This declarative schedule acts as the
# default when nothing has been registered yet via the admin UI.
app.conf.beat_schedule = {
    "dream-check": {
        "task": "scheduler.dream_worker.dream_check",
        "schedule": crontab(minute="*/30"),
    },
    "daily-briefing": {
        "task": "scheduler.tasks.daily_briefing",
        "schedule": crontab(minute=0, hour=8, day_of_week="1-5"),
    },
    "rss-poll": {
        "task": "scheduler.tasks.rss_poll",
        "schedule": crontab(minute="*/30"),
    },
    "future-queue-poll": {
        "task": "scheduler.tasks.future_queue_poll",
        "schedule": crontab(minute="*"),
    },
    "db-backup": {
        "task": "scheduler.tasks.db_backup",
        "schedule": crontab(minute=0, hour=3),
    },
    "approval-expire": {
        "task": "scheduler.tasks.approval_expire",
        "schedule": crontab(minute="*"),
    },
    # Adapted from OpenClaw's cron service: poll the CronJob table every 30s.
    # Lower bound is 30s because crontab() doesn't go finer than a minute and
    # we use a timedelta below so jobs scheduled near a boundary don't drift.
    "cron-job-poll": {
        "task": "scheduler.cron_runner.cron_job_poll",
        "schedule": 30.0,  # seconds
    },
    # Renew Gmail Pub/Sub watch every 24h (the watch itself expires after 7d).
    "gmail-watch-renew": {
        "task": "scheduler.gmail_watch.gmail_watch_renew",
        "schedule": crontab(minute=0, hour=4),
    },
    # IMAP poller for email inbound channel; no-ops if EMAIL_IMAP_HOST is blank.
    "email-poll": {
        "task": "scheduler.email_poller.email_poll",
        "schedule": 120.0,  # every 2 minutes
    },
    # Kanban dispatcher: claim queued tasks and run them.
    "kanban-dispatch": {
        "task": "kanban.worker.kanban_dispatch",
        "schedule": 30.0,
    },
    # Reap stale Kanban claims (worker died mid-task).
    "kanban-reclaim-stale": {
        "task": "kanban.worker.kanban_reclaim_stale",
        "schedule": 300.0,
    },
}


@app.task(bind=True)
def debug_task(self) -> None:
    print(f"Celery debug task request: {self.request!r}")
