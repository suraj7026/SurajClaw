"""GitHub webhook receiver (PR events, issue comments, CI status)."""
from __future__ import annotations

import hashlib
import hmac
import json
import os

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST


def _verify_signature(body: bytes, signature: str) -> bool:
    secret = os.environ.get("GITHUB_WEBHOOK_SECRET", "")
    if not secret:
        return True  # no secret configured means verification is skipped
    expected = "sha256=" + hmac.new(
        secret.encode("utf-8"), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


@csrf_exempt
@require_POST
def receive(request: HttpRequest) -> HttpResponse:
    signature = request.headers.get("X-Hub-Signature-256", "")
    if not _verify_signature(request.body, signature):
        return HttpResponse(status=403)

    event_type = request.headers.get("X-GitHub-Event", "")
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return HttpResponse(status=400)

    from scheduler.tasks import handle_github_event

    handle_github_event.delay(event_type, payload)
    return JsonResponse({"ok": True})
