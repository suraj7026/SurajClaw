"""Gmail push notification receiver (Google Cloud Pub/Sub)."""
from __future__ import annotations

import base64
import json

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST


@csrf_exempt
@require_POST
def receive(request: HttpRequest) -> HttpResponse:
    try:
        envelope = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return HttpResponse(status=400)

    # Pub/Sub push envelope format: {"message": {"data": "<b64>", ...}, ...}
    message = envelope.get("message", {})
    data_b64 = message.get("data", "")
    try:
        decoded = json.loads(base64.b64decode(data_b64).decode("utf-8"))
    except (ValueError, json.JSONDecodeError):
        decoded = {}

    from scheduler.tasks import handle_gmail_push

    handle_gmail_push.delay(decoded)
    return JsonResponse({"ok": True})
