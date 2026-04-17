"""REST API URLs. Populated in `api/views.py` as endpoints are added."""
from __future__ import annotations

from django.urls import path

from api import views

urlpatterns = [
    path("health/", views.health, name="api-health"),
]
