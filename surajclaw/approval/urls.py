"""Approval gate URLs."""
from __future__ import annotations

from django.urls import path

from approval import views

urlpatterns = [
    path("<uuid:request_id>/respond/", views.respond, name="approval-respond"),
]
