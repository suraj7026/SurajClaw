"""Gmail read tools.

All tools are read-only by design (system prompt forbids claiming we sent
mail). Multi-account fan-out via ``account_label="all"`` is the common
case for ``fetch_recent`` and ``search_messages``.
"""
from __future__ import annotations

import base64
from email.utils import parseaddr
from typing import Any

from agents.types import ToolDefinition
from core.google_accounts import GoogleAccount
from tools.google._common import gmail_client, per_account_fanout, single_account, truncate
from tools.registry import register_tool


def _decode_part(data: str) -> str:
    try:
        return base64.urlsafe_b64decode(data.encode("utf-8")).decode("utf-8", errors="replace")
    except Exception:
        return ""


def _walk_parts(payload: dict[str, Any]) -> tuple[str, str]:
    """Return ``(text_plain, text_html)`` extracted from a Gmail message payload."""
    text_plain = ""
    text_html = ""

    def visit(part: dict[str, Any]) -> None:
        nonlocal text_plain, text_html
        mime = part.get("mimeType", "")
        body = part.get("body") or {}
        data = body.get("data")
        if data and mime == "text/plain" and not text_plain:
            text_plain = _decode_part(data)
        elif data and mime == "text/html" and not text_html:
            text_html = _decode_part(data)
        for child in part.get("parts", []) or []:
            visit(child)

    visit(payload or {})
    return text_plain, text_html


def _header(headers: list[dict[str, str]], name: str) -> str:
    name_l = name.lower()
    for h in headers or []:
        if h.get("name", "").lower() == name_l:
            return h.get("value", "")
    return ""


def _format_email(msg: dict[str, Any]) -> dict[str, Any]:
    payload = msg.get("payload") or {}
    headers = payload.get("headers") or []
    text_plain, text_html = _walk_parts(payload)
    name, email = parseaddr(_header(headers, "From"))
    return {
        "message_id": msg.get("id"),
        "thread_id": msg.get("threadId"),
        "subject": _header(headers, "Subject"),
        "from": name or email,
        "from_email": email,
        "to": _header(headers, "To"),
        "date": _header(headers, "Date"),
        "snippet": msg.get("snippet", ""),
        "text_plain": truncate(text_plain, 4000),
        "text_html_preview": truncate(text_html, 600),
        "label_ids": msg.get("labelIds", []),
    }


# ---------------------------------------------------------------------------
# google.gmail.fetch_recent
# ---------------------------------------------------------------------------
def fetch_recent(
    account_label: str = "all",
    query: str = "is:unread newer_than:1d",
    limit: int = 10,
) -> dict[str, Any]:
    """Search Gmail and return full message bodies for the top ``limit`` hits."""
    def _one(account: GoogleAccount) -> dict[str, Any]:
        service = gmail_client(account)
        listing = (
            service.users()
            .messages()
            .list(userId="me", q=query, maxResults=max(1, min(limit, 50)))
            .execute()
        )
        ids = [m.get("id") for m in listing.get("messages", []) if m.get("id")]
        emails = []
        for mid in ids:
            msg = (
                service.users()
                .messages()
                .get(userId="me", id=mid, format="full")
                .execute()
            )
            emails.append(_format_email(msg))
        return {
            "items": emails,
            "output": f"{len(emails)} message(s) for query `{query}`",
        }

    result = per_account_fanout(account_label, _one)
    if result.get("ok"):
        result["structured"]["emails"] = result["structured"].pop("items", [])
    return result


# ---------------------------------------------------------------------------
# google.gmail.search_messages
# ---------------------------------------------------------------------------
def search_messages(
    account_label: str = "all",
    query: str = "",
    limit: int = 20,
) -> dict[str, Any]:
    """Search Gmail and return lightweight headers (no body) for ``limit`` hits."""
    if not query:
        return {"ok": False, "output": "query is required", "error": "missing_query"}

    def _one(account: GoogleAccount) -> dict[str, Any]:
        service = gmail_client(account)
        listing = (
            service.users()
            .messages()
            .list(userId="me", q=query, maxResults=max(1, min(limit, 100)))
            .execute()
        )
        items: list[dict[str, Any]] = []
        for stub in listing.get("messages", []) or []:
            mid = stub.get("id")
            if not mid:
                continue
            msg = (
                service.users()
                .messages()
                .get(userId="me", id=mid, format="metadata", metadataHeaders=["From", "Subject", "Date"])
                .execute()
            )
            headers = (msg.get("payload") or {}).get("headers") or []
            name, email = parseaddr(_header(headers, "From"))
            items.append(
                {
                    "message_id": mid,
                    "thread_id": msg.get("threadId"),
                    "subject": _header(headers, "Subject"),
                    "from": name or email,
                    "from_email": email,
                    "date": _header(headers, "Date"),
                    "snippet": msg.get("snippet", ""),
                }
            )
        return {"items": items, "output": f"{len(items)} match(es) for `{query}`"}

    return per_account_fanout(account_label, _one)


# ---------------------------------------------------------------------------
# google.gmail.get_message
# ---------------------------------------------------------------------------
def get_message(account_label: str, message_id: str) -> dict[str, Any]:
    """Fetch one Gmail message with full headers and body."""
    if not message_id:
        return {"ok": False, "output": "message_id is required", "error": "missing_message_id"}

    def _one(account: GoogleAccount) -> dict[str, Any]:
        service = gmail_client(account)
        msg = (
            service.users()
            .messages()
            .get(userId="me", id=message_id, format="full")
            .execute()
        )
        email = _format_email(msg)
        return {
            "output": f"{email['subject']} ({email['from']})",
            "structured": {"email": email},
        }

    return single_account(account_label, _one)


# ---------------------------------------------------------------------------
# google.gmail.list_threads
# ---------------------------------------------------------------------------
def list_threads(
    account_label: str = "all",
    query: str = "in:inbox",
    limit: int = 20,
) -> dict[str, Any]:
    """List Gmail threads matching ``query``."""
    def _one(account: GoogleAccount) -> dict[str, Any]:
        service = gmail_client(account)
        listing = (
            service.users()
            .threads()
            .list(userId="me", q=query, maxResults=max(1, min(limit, 100)))
            .execute()
        )
        items: list[dict[str, Any]] = []
        for thread in listing.get("threads", []) or []:
            tid = thread.get("id")
            if not tid:
                continue
            items.append(
                {
                    "thread_id": tid,
                    "snippet": thread.get("snippet", ""),
                    "history_id": thread.get("historyId"),
                }
            )
        return {"items": items, "output": f"{len(items)} thread(s) for `{query}`"}

    return per_account_fanout(account_label, _one)


def register() -> None:
    register_tool(ToolDefinition(
        id="google.gmail.fetch_recent",
        callable=fetch_recent,
        description=(
            "Fetch recent Gmail messages with bodies. Args: account_label "
            "(default 'all' fans out across every connected account), "
            "query (Gmail search syntax, e.g. 'is:unread newer_than:1d'), "
            "limit (default 10, max 50). Returns structured.emails."
        ),
    ))
    register_tool(ToolDefinition(
        id="google.gmail.search_messages",
        callable=search_messages,
        description=(
            "Search Gmail and return lightweight headers (no bodies). Args: "
            "account_label, query (Gmail search syntax), limit (default 20)."
        ),
    ))
    register_tool(ToolDefinition(
        id="google.gmail.get_message",
        callable=get_message,
        description=(
            "Fetch one Gmail message with full body. Args: account_label "
            "(single account, no 'all'), message_id."
        ),
    ))
    register_tool(ToolDefinition(
        id="google.gmail.list_threads",
        callable=list_threads,
        description=(
            "List Gmail threads. Args: account_label, query, limit. Returns "
            "thread ids and snippets; use get_message on each message id to read."
        ),
    ))
