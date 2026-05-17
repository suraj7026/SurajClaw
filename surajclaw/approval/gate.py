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
    # Google Calendar
    "google.calendar.create_event",
    "google.calendar.update_event",
    "google.calendar.delete_event",
    # Google Tasks
    "google.tasks.create_task",
    "google.tasks.update_task",
    "google.tasks.delete_task",
    # Google Drive
    "google.drive.create_file",
    "google.drive.update_file",
    "google.drive.delete_file",
    # Google Docs
    "google.docs.create_doc",
    "google.docs.append_text",
    "google.docs.replace_text",
    "google.docs.delete_doc",
    # Google Sheets
    "google.sheets.create_sheet",
    "google.sheets.update_values",
    "google.sheets.append_values",
    "google.sheets.delete_sheet",
    # Coding (spawns the official gemini CLI; consumes Gemini quota + pushes a branch)
    "coding.gemini_cli_run",
    # Coding (spawns Google Antigravity's agentic IDE; pushes a branch)
    "coding.antigravity_run",
    # Browser confirmation gate (used before submitting checkout / payment forms)
    "browser.confirm_purchase",
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


def _dynamic_gate(tool_id: str, args: dict | None) -> bool:
    """Tools whose gating depends on call-time arguments.

    Returns True if the call should be gated. Plain-list-of-ids in
    GATED_TOOLS is the static path; this is the escape hatch for tools
    like ``agents.spawn_subagent`` that are gated only when given certain
    arguments (any non-empty tool grant).
    """
    if tool_id == "agents.spawn_subagent":
        try:
            from tools.agents.spawn import needs_approval

            return bool(needs_approval(args or {}))
        except Exception as exc:  # noqa: BLE001
            logger.warning("dynamic gate for %s failed: %s; defaulting to gated", tool_id, exc)
            return True
    return False


def intercept_if_gated(
    *,
    tool_id: str,
    description: str,
    session_id: str,
    timeout_seconds: int = 600,
    args: dict | None = None,
) -> ApprovalOutcome:
    """If ``tool_id`` is gated (static or dynamic), create an ApprovalRequest and wait.

    Ungated tools return immediately approved. Gated tools create a DB row,
    notify the user, then poll until the row leaves PENDING or the timeout
    elapses.
    """
    if tool_id not in GATED_TOOLS and not _dynamic_gate(tool_id, args):
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
