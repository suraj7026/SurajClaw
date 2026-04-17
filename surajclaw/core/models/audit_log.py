from __future__ import annotations

from django.db import models


class AuditLog(models.Model):
    """Append-only record of every tool invocation.

    IMPORTANT: we deliberately do NOT override .delete() here — individual
    rows remain deletable via the ORM for testing and admin clean-up. In
    production, `core_audit_log` should be granted INSERT and SELECT only
    for the application database user (see ops docs / runbook).

    `input_hash` is a SHA256 of the sanitized tool arguments, so secrets
    never land in the audit trail even for failed calls.
    """

    id = models.BigAutoField(primary_key=True)
    session = models.ForeignKey(
        "core.Session",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_entries",
    )
    tool_id = models.CharField(max_length=128)
    input_hash = models.CharField(max_length=64)
    output_summary = models.CharField(max_length=200, blank=True, default="")
    duration_ms = models.IntegerField(null=True, blank=True)
    approved_by = models.CharField(max_length=128, null=True, blank=True)
    was_gated = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "core_audit_log"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tool_id"]),
            models.Index(fields=["created_at"]),
            models.Index(fields=["session"]),
        ]

    def __str__(self) -> str:
        return f"AuditLog({self.tool_id}@{self.created_at:%Y-%m-%d %H:%M})"
