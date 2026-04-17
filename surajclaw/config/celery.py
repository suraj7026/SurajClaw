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
}


@app.task(bind=True)
def debug_task(self) -> None:
    print(f"Celery debug task request: {self.request!r}")
