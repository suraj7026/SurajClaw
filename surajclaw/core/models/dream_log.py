from __future__ import annotations

import uuid

from django.db import models


class DreamLog(models.Model):
    """One row per Dream consolidation cycle.

    Used for observability (how often is Dream running? what did it
    change?) and as the audit trail for memory-rewriting operations.
    Values come from the `dream_node` after consolidation completes.
    """

    class Trigger(models.TextChoices):
        AUTO = "auto", "Auto"
        MANUAL = "manual", "Manual"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    trigger = models.CharField(max_length=16, choices=Trigger.choices)
    sessions_processed = models.IntegerField(default=0)
    entities_merged = models.IntegerField(default=0)
    entities_pruned = models.IntegerField(default=0)
    notes_updated = models.IntegerField(default=0)
    duration_seconds = models.FloatField(default=0.0)
    summary = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "core_dream_log"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"DreamLog({self.trigger}@{self.created_at:%Y-%m-%d %H:%M})"
