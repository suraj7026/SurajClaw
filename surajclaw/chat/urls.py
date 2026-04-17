"""Web chat HTTP URLs (HTMX index page)."""
from __future__ import annotations

from django.urls import path

from chat import views

urlpatterns = [
    path("", views.index, name="chat-index"),
]
