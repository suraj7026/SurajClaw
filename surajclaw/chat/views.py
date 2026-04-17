"""Web chat HTTP views. The heavy lifting happens in Channels consumers."""
from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render


def index(request: HttpRequest) -> HttpResponse:
    """Render the chat index page; WebSocket handles live messaging."""
    return render(request, "chat/index.html", {})
