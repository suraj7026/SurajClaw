"""Channels WebSocket URL routing."""
from __future__ import annotations

from django.urls import path

from chat import consumers

websocket_urlpatterns = [
    path("ws/chat/<uuid:session_id>/", consumers.ChatConsumer.as_asgi()),
]
