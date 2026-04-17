from __future__ import annotations

import uuid

from django.db import models


class Message(models.Model):
    """One message within a conversation session.

    Roles mirror the LangGraph convention: user, assistant, tool, system.
    `model_used` tracks which backend produced each assistant message so we
    can later audit local vs cloud routing decisions.
    """

    class Role(models.TextChoices):
        USER = "user", "User"
        ASSISTANT = "assistant", "Assistant"
        TOOL = "tool", "Tool"
        SYSTEM = "system", "System"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(
        "core.Session",
        on_delete=models.CASCADE,
        related_name="messages",
    )
    role = models.CharField(max_length=16, choices=Role.choices)
    content = models.TextField()
    model_used = models.CharField(max_length=64, null=True, blank=True)
    tokens_used = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "core_message"
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["session", "created_at"]),
            models.Index(fields=["role"]),
        ]

    def __str__(self) -> str:
        preview = (self.content[:60] + "...") if len(self.content) > 60 else self.content
        return f"Message({self.role}): {preview}"
