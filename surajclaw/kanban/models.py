"""Durable task queue, hermes-style.

A ``KanbanTask`` is an instruction to run a (potentially long) agent turn
that must survive Daphne / worker restarts. The dispatcher claims a queued
task with ``SELECT FOR UPDATE SKIP LOCKED`` so multiple workers can pull
in parallel without double-running.

State machine::

    QUEUED -> CLAIMED -> RUNNING -> DONE | FAILED
                       \\-> CLAIMED  (after reclaim of stale claim)

Stale-claim reaper resets ``CLAIMED`` rows whose ``heartbeat_at`` is older
than ``stale_after_seconds`` back to ``QUEUED`` so they retry on the next
dispatch tick.
"""
from __future__ import annotations

import uuid

from django.db import models


class KanbanTask(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        CLAIMED = "claimed", "Claimed"
        RUNNING = "running", "Running"
        DONE = "done", "Done"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Description shown in CLI / WebUI.
    title = models.CharField(max_length=200)
    # The actual prompt fed to the agent.
    prompt = models.TextField()
    # Optional agent override; if empty, GENERAL is used.
    agent_id = models.CharField(max_length=64, blank=True)
    # Optional model directive (gemini / claude / nim / auto).
    model_provider = models.CharField(max_length=32, blank=True)
    # Free-form context dict passed through to the agent's state.context.
    context = models.JSONField(default=dict, blank=True)

    priority = models.IntegerField(
        default=0,
        help_text="Higher first. Dispatcher orders by (-priority, created_at).",
    )

    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.QUEUED
    )
    claim_id = models.CharField(
        max_length=64,
        blank=True,
        help_text="Worker-supplied token identifying who owns the current claim.",
    )
    claimed_at = models.DateTimeField(null=True, blank=True)
    heartbeat_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    result = models.TextField(blank=True)
    error_text = models.TextField(blank=True)

    attempts = models.PositiveIntegerField(default=0)
    max_attempts = models.PositiveIntegerField(default=3)

    stale_after_seconds = models.PositiveIntegerField(
        default=600,
        help_text="A claim with heartbeat older than this is reset to QUEUED.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    created_by = models.CharField(max_length=128, blank=True)

    class Meta:
        db_table = "kanban_task"
        ordering = ["-priority", "created_at"]
        indexes = [
            models.Index(fields=["status", "priority", "created_at"]),
            models.Index(fields=["status", "heartbeat_at"]),
        ]

    def __str__(self) -> str:
        return f"KanbanTask({self.title!r}, {self.status}, attempts={self.attempts})"
