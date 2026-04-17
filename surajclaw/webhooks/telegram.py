"""Telegram bot webhook receiver.

Telegram POSTs JSON updates here. We validate the shared secret header,
extract the message, and dispatch to the agent via the chat pipeline.
"""
from __future__ import annotations

import json

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST


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

    # Dispatch happens in a Celery task so we return 200 quickly and avoid
    # blocking Telegram's webhook retry logic on long agent runs.
    from scheduler.tasks import handle_telegram_update

    handle_telegram_update.delay(update)
    return JsonResponse({"ok": True})
