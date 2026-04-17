"""Gmail Pub/Sub watch lifecycle (multi-account).

Adapted from OpenClaw's ``src/hooks/gmail-watcher.ts`` and
``gmail-watcher-lifecycle.ts``. Gmail's ``users.watch`` registration expires
**every 7 days**. If we don't re-register, push notifications silently stop
and the user thinks the assistant is broken. So this Celery task fires
every 24 hours, walks every connected Google account, calls ``users.watch``
for each, and records the result in ``SystemState`` so ``/doctor`` can show
the most recent renewal per account.

The actual webhook receiver lives in ``webhooks/gmail_push.py``; this file
only owns the *renewal* side.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from celery import shared_task
from django.conf import settings

from core.google_accounts import GoogleAccount, list_accounts

logger = logging.getLogger(__name__)

# SystemState key prefixes we own; namespaced per account label so two
# Gmail accounts don't clobber each other's renewal timestamps.
def _key(label: str, suffix: str) -> str:
    return f"gmail_watch:{label}:{suffix}"


def _store(key: str, value: str) -> None:
    """Best-effort SystemState upsert. Avoids hard dependency at import time."""
    try:
        from core.models import SystemState
    except ImportError:
        return
    try:
        SystemState.objects.update_or_create(key=key, defaults={"value": value})
    except Exception as exc:  # noqa: BLE001 -- never let bookkeeping crash the task
        logger.debug("failed to record %s: %s", key, exc)


def _build_gmail_service(account: GoogleAccount) -> Any | None:
    """Build a Gmail API client for ``account`` or return ``None``.

    We deliberately don't raise so a deployment with only *some* accounts
    working still has a green Celery worker.
    """
    try:
        from googleapiclient.discovery import build  # type: ignore[import-not-found]
    except ImportError:
        logger.info("google api libs missing; gmail watch renewal skipped")
        return None

    try:
        creds = account.load_credentials(
            scopes=["https://www.googleapis.com/auth/gmail.readonly"],
        )
    except (OSError, KeyError, ValueError) as exc:
        logger.warning("gmail credentials invalid for %s: %s", account.label, exc)
        return None

    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def _renew_one(account: GoogleAccount, topic: str, label_ids: list[str]) -> dict[str, Any]:
    service = _build_gmail_service(account)
    if service is None:
        _store(_key(account.label, "last_error"), "gmail client unavailable")
        return {"ok": False, "account": account.label, "reason": "no_client"}

    request_body = {
        "topicName": topic,
        "labelIds": label_ids,
        # INCLUDE: fire only for the labels we listed (vs. EXCLUDE which
        # would be "everything but these"). INCLUDE is what a personal-inbox
        # workflow almost always wants.
        "labelFilterBehavior": "INCLUDE",
    }

    try:
        response = (
            service.users().watch(userId="me", body=request_body).execute(num_retries=2)
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("gmail watch renew failed for %s", account.label)
        _store(_key(account.label, "last_error"), str(exc)[:512])
        return {"ok": False, "account": account.label, "error": str(exc)[:200]}

    history_id = str(response.get("historyId", ""))
    expiration_ms = int(response.get("expiration", 0))
    expires_at = (
        datetime.fromtimestamp(expiration_ms / 1000, tz=timezone.utc).isoformat()
        if expiration_ms
        else ""
    )
    now_iso = datetime.now(timezone.utc).isoformat()
    _store(_key(account.label, "last_renew_at"), now_iso)
    _store(_key(account.label, "last_history_id"), history_id)
    _store(_key(account.label, "expires_at"), expires_at)
    _store(_key(account.label, "last_error"), "")
    logger.info(
        "gmail watch renewed for %s: history_id=%s expires=%s",
        account.label, history_id, expires_at,
    )
    return {
        "ok": True,
        "account": account.label,
        "history_id": history_id,
        "expires_at": expires_at,
    }


@shared_task(bind=True, max_retries=3, default_retry_delay=300)
def gmail_watch_renew(self) -> dict[str, Any]:
    """Re-register the Gmail Pub/Sub watch for every connected account.

    Body docs:
    https://developers.google.com/gmail/api/reference/rest/v1/users/watch

    Required env (read via settings):

    * ``GMAIL_PUBSUB_TOPIC`` — full topic name, e.g.
      ``projects/my-proj/topics/gmail-push``. Shared across accounts.
    * Optional ``GMAIL_LABEL_IDS`` — JSON array of label ids to filter
      (default: ``["INBOX"]``).
    """
    topic = getattr(settings, "GMAIL_PUBSUB_TOPIC", "")
    if not topic:
        logger.info("GMAIL_PUBSUB_TOPIC unset; skipping renew")
        _store("gmail_watch:last_error", "GMAIL_PUBSUB_TOPIC unset")
        return {"ok": False, "reason": "topic_unset"}

    label_ids_raw = getattr(settings, "GMAIL_LABEL_IDS", "")
    try:
        label_ids = json.loads(label_ids_raw) if label_ids_raw else ["INBOX"]
    except json.JSONDecodeError:
        label_ids = ["INBOX"]

    accounts = list_accounts()
    if not accounts:
        logger.info("no connected google accounts; skipping gmail watch renew")
        _store("gmail_watch:last_error", "no connected accounts")
        return {"ok": False, "reason": "no_accounts"}

    results = [_renew_one(acc, topic, label_ids) for acc in accounts]
    any_failed = any(not r["ok"] for r in results)

    # Only trigger Celery's retry if *every* account failed — otherwise we'd
    # re-renew healthy accounts on every retry and thrash the Gmail API.
    if any_failed and all(not r["ok"] for r in results):
        try:
            raise self.retry(countdown=300 * (2**self.request.retries))
        except self.MaxRetriesExceededError:
            return {"ok": False, "results": results, "reason": "max_retries"}

    return {"ok": not any_failed, "results": results}
