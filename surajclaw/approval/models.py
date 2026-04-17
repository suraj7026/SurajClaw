"""Approval gate model: pending human-in-the-loop decisions."""
from __future__ import annotations

import uuid
from datetime import timedelta

from django.db import models
from django.utils import timezone


def _default_expires_at():
    return timezone.now() + timedelta(minutes=10)


class ApprovalRequest(models.Model):
    """One pending destructive tool call awaiting user confirmation.

    The agent's approval_gate creates a row, pushes a notification
    (Telegram + WebSocket), then blocks until either
    (a) the user POSTs to /approval/<id>/respond/, or
    (b) `expires_at` passes and the periodic `approval_expire` task
        marks this row as `expired`.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        EXPIRED = "expired", "Expired"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(
        "core.Session",
        on_delete=models.CASCADE,
        related_name="approval_requests",
    )
    tool_id = models.CharField(max_length=128)
    description = models.TextField()
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING
    )
    responded_by = models.CharField(max_length=128, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(default=_default_expires_at)

    class Meta:
        db_table = "approval_request"
        ordering = ["-created_at"]
        indexes = [
            # Poller query shape: status=pending AND expires_at < now()
            models.Index(fields=["status", "expires_at"]),
        ]

    def __str__(self) -> str:
        return f"ApprovalRequest({self.tool_id}: {self.status})"
