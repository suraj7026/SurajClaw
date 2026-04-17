"""Telegram bot webhook receiver.

Telegram POSTs JSON updates here. We:

1. Validate the shared secret header.
2. Extract sender id and message text.
3. Reject non-owner senders fast (HTTP 200 still — Telegram will not retry,
   and we don't want anyone probing to get a different response shape).
4. Hand off to a Celery task for the actual agent work.

The Celery task itself runs the same slash-command + directive pipeline as
the web chat consumer, so ``/help`` works equally on Telegram.
"""
from __future__ import annotations

import json
import logging

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from chat.auth import is_owner

logger = logging.getLogger(__name__)


def _extract_sender(update: dict) -> tuple[str | None, str | None, str]:
    """Return (sender_id, chat_id, text) from a Telegram update payload."""
    msg = update.get("message") or update.get("edited_message") or {}
    sender = (msg.get("from") or {}).get("id")
    chat = (msg.get("chat") or {}).get("id")
    text = msg.get("text") or msg.get("caption") or ""
    return (
        str(sender) if sender is not None else None,
        str(chat) if chat is not None else None,
        text,
    )


@csrf_exempt
@require_POST
def receive(request: HttpRequest) -> HttpResponse:
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if settings.TELEGRAM_WEBHOOK_SECRET and secret != settings.TELEGRAM_WEBHOOK_SECRET:
        return HttpResponse(status=403)

    try:
        update = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return HttpResponse(status=400)

    sender_id, chat_id, text = _extract_sender(update)
    if not is_owner("telegram", sender_id):
        # Always 200 to discourage probing; Telegram won't retry.
        logger.warning(
            "telegram: rejecting non-owner sender=%s chat=%s",
            sender_id,
            chat_id,
        )
        return JsonResponse({"ok": True, "ignored": True})

    # Dispatch happens in a Celery task so we return 200 quickly and avoid
    # blocking Telegram's webhook retry logic on long agent runs.
    from scheduler.tasks import handle_telegram_update

    handle_telegram_update.delay(
        update,
        sender_id=sender_id,
        chat_id=chat_id,
        text=text,
    )
    return JsonResponse({"ok": True})
