"""CronRun: append-only history of one CronJob firing.

Adapted from OpenClaw's ``src/cron/run-log.ts``. Keeping this in a sibling
table (rather than overwriting fields on CronJob) means we can:

* Show a per-job timeline in the admin.
* Compute success rates without losing prior outcomes.
* Throttle failure alerts based on actual recent runs, not a flag bit.
"""
from __future__ import annotations

import uuid

from django.db import models


class CronRun(models.Model):
    class Status(models.TextChoices):
        OK = "ok", "Success"
        ERROR = "error", "Error"
        SKIPPED = "skipped", "Skipped"
        TIMEOUT = "timeout", "Timed out"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job = models.ForeignKey(
        "core.CronJob",
        on_delete=models.CASCADE,
        related_name="runs",
    )
    status = models.CharField(max_length=12, choices=Status.choices)
    started_at = models.DateTimeField()
    finished_at = models.DateTimeField(null=True, blank=True)
    duration_ms = models.PositiveIntegerField(null=True, blank=True)

    # Telemetry: which model handled it and what it cost.
    model_used = models.CharField(max_length=64, blank=True)
    provider_used = models.CharField(max_length=32, blank=True)
    input_tokens = models.PositiveIntegerField(null=True, blank=True)
    output_tokens = models.PositiveIntegerField(null=True, blank=True)

    # Outcome.
    summary = models.TextField(blank=True)
    error_text = models.TextField(blank=True)
    delivery_status = models.CharField(
        max_length=16,
        blank=True,
        help_text="delivered | not-delivered | not-requested",
    )

    class Meta:
        db_table = "core_cron_run"
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["job", "-started_at"]),
            models.Index(fields=["status", "-started_at"]),
        ]

    def __str__(self) -> str:
        return f"CronRun({self.job_id}, {self.status}@{self.started_at:%Y-%m-%d %H:%M})"
