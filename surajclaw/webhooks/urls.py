"""Inbound webhook URLs (Telegram, GitHub, Gmail push)."""
from __future__ import annotations

from django.urls import path

from webhooks import telegram, github, gmail_push

urlpatterns = [
    path("telegram/", telegram.receive, name="webhook-telegram"),
    path("github/", github.receive, name="webhook-github"),
    path("gmail-push/", gmail_push.receive, name="webhook-gmail-push"),
]
