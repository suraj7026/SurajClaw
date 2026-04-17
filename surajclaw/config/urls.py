"""Root URL configuration for SurajClaw."""
from __future__ import annotations

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("api.urls")),
    path("webhooks/", include("webhooks.urls")),
    path("approval/", include("approval.urls")),
    path("", include("chat.urls")),
]
