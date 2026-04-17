"""Custom tools: agent-authored tools that can be hot-loaded at runtime.

The agent is allowed to propose new tools (e.g. "scrape the BBC RSS daily
and summarize"). Proposed tools land here, are validated (sandbox run), and
then `loader.py` wires them into the LangGraph tool registry.
"""
from __future__ import annotations

import uuid

from django.db import models


class CustomTool(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=128, unique=True)
    description = models.TextField()
    source_code = models.TextField()
    is_active = models.BooleanField(default=True)
    is_validated = models.BooleanField(default=False)
    created_by_session = models.ForeignKey(
        "core.Session",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="custom_tools",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "custom_tools_tool"
        ordering = ["name"]
        indexes = [
            models.Index(fields=["is_active", "is_validated"]),
        ]

    def __str__(self) -> str:
        return self.name
