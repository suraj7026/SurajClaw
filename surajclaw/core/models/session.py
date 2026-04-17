from __future__ import annotations

import uuid

from django.db import models


class Session(models.Model):
    """One conversation session. A session groups messages and belongs to a source.

    Sessions are created on the first inbound message from a given source and
    closed after an idle timeout (the reflector node writes the summary then).
    """

    class Source(models.TextChoices):
        TELEGRAM = "telegram", "Telegram"
        WEB = "web", "Web Chat"
        CRON = "cron", "Cron Scheduled"
        TRIGGER = "trigger", "Event Trigger"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source = models.CharField(max_length=16, choices=Source.choices)
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    summary = models.TextField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "core_session"
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["is_active", "started_at"]),
            models.Index(fields=["source"]),
        ]

    def __str__(self) -> str:
        return f"Session({self.source}, {self.started_at:%Y-%m-%d %H:%M})"
