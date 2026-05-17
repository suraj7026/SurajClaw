"""Pairing flow models.

Inspired by hermes-agent's pairing system and openclaw's ``allowFrom``
scheme: a new device / sender introduces itself, gets a short code, the
owner approves it from CLI / WebUI, and from then on it's allowed without
re-pairing. The DB takes over from the static ``OWNER_ALLOW_FROM`` env
var so you can grant access from a phone while you're on the road.

Two tables:

* ``PairingCode`` -- short-lived, single-use challenge tokens.
* ``ApprovedSender`` -- durable allowlist rows the gate checks alongside
  ``settings.OWNER_ALLOW_FROM``.
"""
from __future__ import annotations

import secrets
import uuid
from datetime import timedelta

from django.db import models
from django.utils import timezone


# Hermes-style unambiguous alphabet (no 0/O/1/I) so codes are readable
# over voice / handwriting.
_PAIRING_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_CODE_LEN = 8


def _generate_code() -> str:
    return "".join(secrets.choice(_PAIRING_ALPHABET) for _ in range(_CODE_LEN))


def _default_expires_at():
    return timezone.now() + timedelta(hours=1)


class PairingCode(models.Model):
    """Pending pairing challenge.

    Created when an unknown ``(channel, sender_id)`` pair contacts SurajClaw.
    Owner approves out-of-band by typing the code at CLI / WebUI. On approval
    we materialize an ``ApprovedSender`` row and consume this challenge.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        DENIED = "denied", "Denied"
        EXPIRED = "expired", "Expired"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=16, unique=True, default=_generate_code)
    channel = models.CharField(max_length=32, db_index=True)
    sender_id = models.CharField(max_length=128, db_index=True)
    display_name = models.CharField(max_length=128, blank=True)

    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.PENDING
    )
    expires_at = models.DateTimeField(default=_default_expires_at)
    created_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)
    responded_by = models.CharField(max_length=128, blank=True)

    class Meta:
        db_table = "pairing_code"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["channel", "sender_id", "status"]),
            models.Index(fields=["status", "expires_at"]),
        ]

    def __str__(self) -> str:
        return f"PairingCode({self.channel}:{self.sender_id}, {self.code}, {self.status})"

    @property
    def is_expired(self) -> bool:
        return self.expires_at <= timezone.now()


class ApprovedSender(models.Model):
    """Durable allowlist row (channel, sender_id) -> the owner trusts it."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    channel = models.CharField(max_length=32)
    sender_id = models.CharField(max_length=128)
    label = models.CharField(
        max_length=128,
        blank=True,
        help_text="Human-readable nickname for the device or person.",
    )
    approved_via_code = models.ForeignKey(
        PairingCode,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="resulting_senders",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_reason = models.CharField(max_length=256, blank=True)

    class Meta:
        db_table = "pairing_approved_sender"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["channel", "sender_id"],
                condition=models.Q(revoked_at__isnull=True),
                name="uniq_active_sender_per_channel",
            ),
        ]
        indexes = [
            models.Index(fields=["channel", "sender_id"]),
        ]

    def __str__(self) -> str:
        suffix = " (revoked)" if self.revoked_at else ""
        return f"ApprovedSender({self.channel}:{self.sender_id}{suffix})"
