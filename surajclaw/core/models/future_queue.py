from __future__ import annotations

import uuid

from django.db import models


class FutureQueue(models.Model):
    """Deferred intentions the agent will act on later.

    Polled every minute by `scheduler.tasks.future_queue_poll`. When a row's
    `due_at` is in the past (and status is still pending) the worker fires
    the intent as a new agent turn and marks the row `fired`.
    """

    class TriggerType(models.TextChoices):
        TIME = "time", "Time-based"
        EVENT = "event", "Event-based"
        MANUAL = "manual", "Manual"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        FIRED = "fired", "Fired"
        CANCELLED = "cancelled", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    intent = models.TextField()
    due_at = models.DateTimeField(null=True, blank=True)
    trigger_type = models.CharField(
        max_length=16, choices=TriggerType.choices, default=TriggerType.TIME
    )
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING
    )
    source_session = models.ForeignKey(
        "core.Session",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="future_items",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "core_future_queue"
        ordering = ["due_at"]
        indexes = [
            # Poller query shape: status=pending AND due_at <= now()
            models.Index(fields=["status", "due_at"]),
        ]

    def __str__(self) -> str:
        preview = (self.intent[:50] + "...") if len(self.intent) > 50 else self.intent
        return f"FutureQueue({self.status}@{self.due_at}): {preview}"
