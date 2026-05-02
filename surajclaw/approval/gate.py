"""Approval gate logic: ask-for-confirmation then block until answered.

Used by any tool that mutates outside state (send email, commit code,
modify a calendar). The agent wraps such tool calls in `intercept_if_gated`;
that helper creates an ApprovalRequest, notifies the user, and waits.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Iterable

from django.utils import timezone

logger = logging.getLogger(__name__)


# Tool ids that require confirmation before running. Kept small and explicit;
# anything destructive MUST be listed.
GATED_TOOLS: set[str] = {
    "gmail_send",
    "gcal_create",
    "gtasks_create",
    "gtasks_complete",
    "gdocs_create",
    "gsheets_write",
    "gdrive_upload",
    "github_merge",
    "github_issue_create",
    "shell_exec",
    "fs_write",
    "fs_delete",
    "google.calendar.delete_event",
    "google.tasks.delete_task",
    "google.drive.delete_file",
    "google.docs.delete_doc",
    "google.sheets.delete_sheet",
}


@dataclass
class ApprovalOutcome:
    approved: bool
    status: str
    responded_by: str | None


def _notify(approval_id: str, description: str, session_id: str) -> None:
    """Push approval prompt to the active WebSocket connection (best-effort)."""
    try:
        from chat.streaming import notify_session

        notify_session(
            session_id,
            {"type": "approval", "request_id": approval_id, "description": description},
        )
    except (ImportError, RuntimeError) as exc:
        logger.warning("approval notify failed: %s", exc)


def intercept_if_gated(
    *,
    tool_id: str,
    description: str,
    session_id: str,
    timeout_seconds: int = 600,
) -> ApprovalOutcome:
    """If `tool_id` is in GATED_TOOLS, create an ApprovalRequest and wait.

    For ungated tools we return immediately with approved=True. For gated
    tools we poll the DB (simple, robust) until the row is no longer
    pending or the timeout elapses.
    """
    if tool_id not in GATED_TOOLS:
        return ApprovalOutcome(approved=True, status="auto", responded_by="auto")

    from approval.models import ApprovalRequest

    ar = ApprovalRequest.objects.create(
        session_id=session_id,
        tool_id=tool_id,
        description=description,
    )
    _notify(str(ar.id), description, session_id)

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        ar.refresh_from_db()
        if ar.status != ApprovalRequest.Status.PENDING:
            return ApprovalOutcome(
                approved=(ar.status == ApprovalRequest.Status.APPROVED),
                status=ar.status,
                responded_by=ar.responded_by,
            )
        time.sleep(1.5)

    # Timeout: mark expired so the periodic task doesn't re-process.
    ar.status = ApprovalRequest.Status.EXPIRED
    ar.responded_at = timezone.now()
    ar.save(update_fields=["status", "responded_at"])
    return ApprovalOutcome(approved=False, status="expired", responded_by=None)


def notify_responded(request_id: str) -> None:
    """Hook called by the respond view when a decision is recorded.

    Currently a no-op placeholder because `intercept_if_gated` uses DB
    polling. If we migrate to channel-layer signalling or condition
    variables, this is where the wake-up fires.
    """
    logger.debug("approval responded: %s", request_id)


def iter_expired(expired_at_cutoff) -> Iterable:
    from approval.models import ApprovalRequest

    return ApprovalRequest.objects.filter(
        status=ApprovalRequest.Status.PENDING,
        expires_at__lt=expired_at_cutoff,
    )
