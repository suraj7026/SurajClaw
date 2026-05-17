"""CronJob: upgraded scheduling table inspired by OpenClaw's `src/cron/types.ts`.

Where ``FutureQueue`` is one-shot ("do X at time T"), ``CronJob`` is recurring
or recurring-with-deadline. Each row owns:

* a *schedule* discriminated union (``at`` / ``every`` / ``cron``),
* a *delivery target* (where to send the resulting message),
* a *failure alert* with a cooldown so a broken job doesn't spam the user,
* its own *next_run_at* the poller advances after each fire.

Run history (model + tokens used, error text, summary) lives in the sibling
:class:`core.models.cron_run.CronRun` table so this row stays cheap to read.
"""
from __future__ import annotations

import uuid

from django.db import models


class CronJob(models.Model):
    class ScheduleKind(models.TextChoices):
        AT = "at", "Run once at"
        EVERY = "every", "Every interval"
        CRON = "cron", "Cron expression"

    class DeliveryMode(models.TextChoices):
        NONE = "none", "None"
        ANNOUNCE = "announce", "Announce on a channel"
        WEBHOOK = "webhook", "POST to webhook URL"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        PAUSED = "paused", "Paused"
        DISABLED = "disabled", "Disabled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=128, unique=True)
    description = models.TextField(blank=True)

    # ---- schedule ---------------------------------------------------------
    schedule_kind = models.CharField(max_length=8, choices=ScheduleKind.choices)
    # For AT: ISO8601 timestamp. For EVERY: integer milliseconds. For CRON:
    # 5- or 6-field crontab expression.
    schedule_value = models.CharField(max_length=128)
    timezone = models.CharField(max_length=64, default="UTC")
    # Deterministic stagger window (seconds) to prevent thundering herd when
    # several jobs share the same cron expression. 0 = exact schedule.
    stagger_seconds = models.PositiveIntegerField(default=0)

    # ---- payload ---------------------------------------------------------
    # The agent message to dispatch. Treat as a system event when no model
    # call is needed (e.g. db_backup), agentTurn otherwise.
    prompt = models.TextField(blank=True)
    light_context = models.BooleanField(
        default=False,
        help_text="If true, run with stripped-down context (faster, no memory load).",
    )
    tools_allow = models.JSONField(default=list, blank=True)

    # ---- delivery --------------------------------------------------------
    delivery_mode = models.CharField(
        max_length=12,
        choices=DeliveryMode.choices,
        default=DeliveryMode.NONE,
    )
    delivery_channel = models.CharField(max_length=32, blank=True)
    delivery_to = models.CharField(max_length=256, blank=True)
    delivery_webhook_url = models.URLField(blank=True)
    # Hermes parity: optional multi-target delivery. Each entry is a dict like
    #   {"channel": "telegram", "to": "-100123"}
    #   {"channel": "webhook",  "url": "https://hooks.example/x"}
    #   {"channel": "email",    "to": "you@example.com"}
    #   {"channel": "log"}                          (just record in CronRun)
    # When non-empty this supersedes the single delivery_* fields above.
    delivery_targets = models.JSONField(default=list, blank=True)

    # ---- model override (Hermes-style per-job routing) -------------------
    # If set, this string is passed to the model router as the directive
    # model for the job's turn. Accepted: "gemini", "claude", "nim", "auto",
    # or a fully-qualified model id. Lets nightly heavy jobs go to a cheap
    # free-tier model (NIM) while interactive chat stays on Gemini/Claude.
    model_provider = models.CharField(max_length=64, blank=True)

    # ---- output capture --------------------------------------------------
    capture_output = models.BooleanField(
        default=True,
        help_text="If true, the agent's final response is stored in CronRun.summary.",
    )

    # ---- failure alerting (per OpenClaw cron failure-alert pattern) ------
    fail_alert_after = models.PositiveIntegerField(
        default=3,
        help_text="Send an alert after N consecutive failures.",
    )
    fail_alert_cooldown_seconds = models.PositiveIntegerField(
        default=3600,
        help_text="Min seconds between failure alerts to avoid spam.",
    )
    last_failure_alert_at = models.DateTimeField(null=True, blank=True)
    consecutive_failures = models.PositiveIntegerField(default=0)

    # ---- runtime state ---------------------------------------------------
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.ACTIVE
    )
    next_run_at = models.DateTimeField(null=True, blank=True)
    last_run_at = models.DateTimeField(null=True, blank=True)
    last_run_status = models.CharField(max_length=16, blank=True)
    running_since = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Set when a worker picks up the job; cleared on completion. "
        "Used to guard against duplicate concurrent runs.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "core_cron_job"
        ordering = ["next_run_at"]
        indexes = [
            # Poller hot path: status=active AND next_run_at <= now() AND running_since IS NULL.
            models.Index(fields=["status", "next_run_at"]),
        ]

    def __str__(self) -> str:
        return f"CronJob({self.name}, {self.schedule_kind}={self.schedule_value})"
