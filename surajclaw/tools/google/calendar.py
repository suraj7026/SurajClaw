"""Google Calendar tools.

Read: list_events (fan-out). Write/destructive: create_event, update_event,
delete_event — gated via approval/gate.GATED_TOOLS.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from agents.types import ToolDefinition
from core.google_accounts import GoogleAccount
from tools.google._common import calendar_client, per_account_fanout, single_account
from tools.registry import register_tool


def _now_rfc3339() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _plus_days(days: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat().replace("+00:00", "Z")


def list_events(
    account_label: str = "all",
    calendar_id: str = "primary",
    time_min: str = "",
    time_max: str = "",
    days_ahead: int = 7,
    query: str = "",
    limit: int = 20,
) -> dict[str, Any]:
    """List upcoming events on ``calendar_id``."""
    tmin = time_min or _now_rfc3339()
    tmax = time_max or _plus_days(max(1, days_ahead))

    def _one(account: GoogleAccount) -> dict[str, Any]:
        service = calendar_client(account)
        kwargs: dict[str, Any] = {
            "calendarId": calendar_id,
            "timeMin": tmin,
            "timeMax": tmax,
            "singleEvents": True,
            "orderBy": "startTime",
            "maxResults": max(1, min(limit, 100)),
        }
        if query:
            kwargs["q"] = query
        result = service.events().list(**kwargs).execute()
        items = []
        for ev in result.get("items", []) or []:
            start = (ev.get("start") or {}).get("dateTime") or (ev.get("start") or {}).get("date")
            end = (ev.get("end") or {}).get("dateTime") or (ev.get("end") or {}).get("date")
            items.append(
                {
                    "event_id": ev.get("id"),
                    "summary": ev.get("summary", ""),
                    "start": start,
                    "end": end,
                    "location": ev.get("location", ""),
                    "html_link": ev.get("htmlLink", ""),
                    "attendees": [a.get("email", "") for a in (ev.get("attendees") or [])],
                }
            )
        return {"items": items, "output": f"{len(items)} event(s) on {calendar_id}"}

    return per_account_fanout(account_label, _one)


def create_event(
    account_label: str,
    summary: str,
    start: str,
    end: str,
    calendar_id: str = "primary",
    description: str = "",
    location: str = "",
    attendees: list[str] | None = None,
) -> dict[str, Any]:
    """Create a single calendar event. ``start`` / ``end`` are RFC3339 strings."""
    if not summary or not start or not end:
        return {"ok": False, "output": "summary, start, end are required", "error": "missing_args"}

    body: dict[str, Any] = {
        "summary": summary,
        "start": {"dateTime": start},
        "end": {"dateTime": end},
    }
    if description:
        body["description"] = description
    if location:
        body["location"] = location
    if attendees:
        body["attendees"] = [{"email": a} for a in attendees]

    def _one(account: GoogleAccount) -> dict[str, Any]:
        service = calendar_client(account)
        ev = service.events().insert(calendarId=calendar_id, body=body).execute()
        return {
            "output": f"created '{summary}' ({ev.get('htmlLink')})",
            "structured": {"event_id": ev.get("id"), "html_link": ev.get("htmlLink")},
        }

    return single_account(account_label, _one)


def update_event(
    account_label: str,
    event_id: str,
    calendar_id: str = "primary",
    summary: str = "",
    start: str = "",
    end: str = "",
    description: str = "",
    location: str = "",
) -> dict[str, Any]:
    """Patch fields on an existing event. Only non-empty args are applied."""
    if not event_id:
        return {"ok": False, "output": "event_id is required", "error": "missing_event_id"}

    patch: dict[str, Any] = {}
    if summary:
        patch["summary"] = summary
    if start:
        patch["start"] = {"dateTime": start}
    if end:
        patch["end"] = {"dateTime": end}
    if description:
        patch["description"] = description
    if location:
        patch["location"] = location
    if not patch:
        return {"ok": False, "output": "no fields to update", "error": "empty_patch"}

    def _one(account: GoogleAccount) -> dict[str, Any]:
        service = calendar_client(account)
        ev = service.events().patch(calendarId=calendar_id, eventId=event_id, body=patch).execute()
        return {
            "output": f"updated event {event_id}",
            "structured": {"event_id": ev.get("id"), "html_link": ev.get("htmlLink")},
        }

    return single_account(account_label, _one)


def delete_event(
    account_label: str,
    event_id: str,
    calendar_id: str = "primary",
) -> dict[str, Any]:
    """Delete a single calendar event. Gated for approval."""
    if not event_id:
        return {"ok": False, "output": "event_id is required", "error": "missing_event_id"}

    def _one(account: GoogleAccount) -> dict[str, Any]:
        service = calendar_client(account)
        service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
        return {"output": f"deleted event {event_id}", "structured": {"event_id": event_id}}

    return single_account(account_label, _one)


def register() -> None:
    register_tool(ToolDefinition(
        id="google.calendar.list_events",
        callable=list_events,
        description=(
            "List Calendar events between time_min/time_max (RFC3339) or for the "
            "next days_ahead days. Args: account_label, calendar_id (default "
            "'primary'), time_min, time_max, days_ahead, query, limit."
        ),
    ))
    register_tool(ToolDefinition(
        id="google.calendar.create_event",
        callable=create_event,
        description=(
            "Create a new event. Args: account_label (single), summary, start, "
            "end (RFC3339), optional description, location, attendees (list of "
            "emails), calendar_id."
        ),
        approval_required=True,
    ))
    register_tool(ToolDefinition(
        id="google.calendar.update_event",
        callable=update_event,
        description=(
            "Patch an existing event. Args: account_label, event_id, optional "
            "summary, start, end, description, location."
        ),
        approval_required=True,
    ))
    register_tool(ToolDefinition(
        id="google.calendar.delete_event",
        callable=delete_event,
        description="Delete an event. Args: account_label, event_id, calendar_id.",
        approval_required=True,
    ))
