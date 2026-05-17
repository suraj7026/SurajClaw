"""Service layer for the pairing flow.

Used by:

* ``chat.auth.is_owner`` (consults ``ApprovedSender`` DB rows).
* CLI / WebUI / management commands (approve/deny by code).
* Inbound channels that want to *initiate* pairing for a stranger.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Optional

from django.db import transaction
from django.utils import timezone


def is_approved(channel: str, sender_id: str | int) -> bool:
    """Return True if ``(channel, sender_id)`` has an active ApprovedSender row."""
    from pairing.models import ApprovedSender

    if not channel or sender_id is None:
        return False
    try:
        return ApprovedSender.objects.filter(
            channel=channel.strip().lower(),
            sender_id=str(sender_id).strip().lower(),
            revoked_at__isnull=True,
        ).exists()
    except Exception:
        # DB might be mid-migration; fail closed but don't crash.
        return False


def start_pairing(
    channel: str,
    sender_id: str | int,
    display_name: str = "",
    ttl_minutes: int = 60,
):
    """Create or refresh a pending PairingCode for ``(channel, sender_id)``.

    If a pending row already exists and isn't expired, return it (idempotent).
    Returns the ``PairingCode`` row -- callers display the ``.code`` to the
    sender so they can read it back to the owner.
    """
    from pairing.models import PairingCode

    channel = (channel or "").strip().lower()
    sid = str(sender_id).strip().lower()

    existing = (
        PairingCode.objects.filter(
            channel=channel,
            sender_id=sid,
            status=PairingCode.Status.PENDING,
        )
        .order_by("-created_at")
        .first()
    )
    if existing and not existing.is_expired:
        return existing

    return PairingCode.objects.create(
        channel=channel,
        sender_id=sid,
        display_name=display_name[:128],
        expires_at=timezone.now() + timedelta(minutes=ttl_minutes),
    )


def list_pending() -> list:
    from pairing.models import PairingCode

    return list(
        PairingCode.objects.filter(
            status=PairingCode.Status.PENDING,
            expires_at__gt=timezone.now(),
        ).order_by("-created_at")
    )


@transaction.atomic
def approve_code(code: str, responded_by: str = "owner", label: str = ""):
    """Materialize an ApprovedSender from a PairingCode (case-insensitive).

    Returns ``(ApprovedSender, PairingCode)`` on success, raises ``ValueError``
    otherwise so callers (CLI, WebUI, API) can render a clean error.
    """
    from pairing.models import ApprovedSender, PairingCode

    code_normalized = (code or "").strip().upper()
    if not code_normalized:
        raise ValueError("empty code")

    try:
        pc = PairingCode.objects.select_for_update().get(code=code_normalized)
    except PairingCode.DoesNotExist as exc:
        raise ValueError(f"no pairing code {code_normalized!r}") from exc

    if pc.status != PairingCode.Status.PENDING:
        raise ValueError(f"code is {pc.status}, not pending")
    if pc.is_expired:
        pc.status = PairingCode.Status.EXPIRED
        pc.save(update_fields=["status"])
        raise ValueError("code expired")

    pc.status = PairingCode.Status.APPROVED
    pc.responded_at = timezone.now()
    pc.responded_by = responded_by[:128]
    pc.save(update_fields=["status", "responded_at", "responded_by"])

    sender, _ = ApprovedSender.objects.get_or_create(
        channel=pc.channel,
        sender_id=pc.sender_id,
        revoked_at__isnull=True,
        defaults={
            "label": (label or pc.display_name or pc.sender_id)[:128],
            "approved_via_code": pc,
        },
    )
    return sender, pc


@transaction.atomic
def deny_code(code: str, responded_by: str = "owner") -> "PairingCode":
    from pairing.models import PairingCode

    code_normalized = (code or "").strip().upper()
    pc = PairingCode.objects.select_for_update().get(code=code_normalized)
    if pc.status != PairingCode.Status.PENDING:
        raise ValueError(f"code is {pc.status}, not pending")
    pc.status = PairingCode.Status.DENIED
    pc.responded_at = timezone.now()
    pc.responded_by = responded_by[:128]
    pc.save(update_fields=["status", "responded_at", "responded_by"])
    return pc


@transaction.atomic
def revoke_sender(
    channel: str,
    sender_id: str | int,
    reason: str = "",
) -> Optional["ApprovedSender"]:
    from pairing.models import ApprovedSender

    sender = (
        ApprovedSender.objects.select_for_update()
        .filter(
            channel=channel.strip().lower(),
            sender_id=str(sender_id).strip().lower(),
            revoked_at__isnull=True,
        )
        .first()
    )
    if not sender:
        return None
    sender.revoked_at = timezone.now()
    sender.revoked_reason = reason[:256]
    sender.save(update_fields=["revoked_at", "revoked_reason"])
    return sender


def list_approved(channel: str = "") -> list:
    from pairing.models import ApprovedSender

    qs = ApprovedSender.objects.filter(revoked_at__isnull=True)
    if channel:
        qs = qs.filter(channel=channel.strip().lower())
    return list(qs.order_by("channel", "sender_id"))
