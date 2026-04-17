from __future__ import annotations

from django.db import models


class SystemState(models.Model):
    """Small key-value store for system-wide runtime state.

    Used for values like `last_dream_at`, `last_dream_session_count`,
    `dream_lock`, and `schema_version`. Kept deliberately simple so any
    process (web, Celery worker, Beat) can read/write consistently through
    the ORM.
    """

    key = models.CharField(max_length=128, primary_key=True)
    value = models.TextField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "core_system_state"

    def __str__(self) -> str:
        return f"{self.key}={self.value[:40]}"

    @classmethod
    def get(cls, key: str, default: str | None = None) -> str | None:
        try:
            return cls.objects.get(pk=key).value
        except cls.DoesNotExist:
            return default

    @classmethod
    def set(cls, key: str, value: str) -> "SystemState":
        obj, _ = cls.objects.update_or_create(pk=key, defaults={"value": value})
        return obj
