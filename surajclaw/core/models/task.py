from __future__ import annotations

import uuid

from django.db import models


class Task(models.Model):
    """Every completed agent request becomes a Task row.

    The `tools_used` JSON list gives us a fast way to answer queries like
    "show me everything where gdocs_create ran" without joining against
    AuditLog. Status transitions: pending -> running -> done | failed.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        DONE = "done", "Done"
        FAILED = "failed", "Failed"

    class Source(models.TextChoices):
        TELEGRAM = "telegram", "Telegram"
        WEB = "web", "Web Chat"
        CRON = "cron", "Cron"
        TRIGGER = "trigger", "Trigger"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(
        "core.Session",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tasks",
    )
    source = models.CharField(max_length=16, choices=Source.choices)
    request = models.TextField()
    result = models.TextField(null=True, blank=True)
    tools_used = models.JSONField(default=list, blank=True)
    tokens_used = models.IntegerField(null=True, blank=True)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING
    )
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "core_task"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["created_at"]),
            models.Index(fields=["source"]),
        ]

    def __str__(self) -> str:
        preview = (self.request[:50] + "...") if len(self.request) > 50 else self.request
        return f"Task({self.status}): {preview}"
