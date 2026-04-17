"""REST API URLs.

Public/health endpoints stay as bare function views; everything else hangs
off a DRF router so we get list/retrieve/detail URLs (and any custom
@action) for free.
"""
from __future__ import annotations

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from api import auth, doctor, google, viewsets, views

router = DefaultRouter()
router.register(r"sessions", viewsets.SessionViewSet, basename="session")
router.register(r"messages", viewsets.MessageViewSet, basename="message")
router.register(r"tasks", viewsets.TaskViewSet, basename="task")
router.register(r"cron-jobs", viewsets.CronJobViewSet, basename="cron-job")
router.register(r"cron-runs", viewsets.CronRunViewSet, basename="cron-run")
router.register(r"future-queue", viewsets.FutureQueueViewSet, basename="future-queue")
router.register(r"memory/entities", viewsets.EntityViewSet, basename="entity")
router.register(r"memory/notes", viewsets.NoteIndexViewSet, basename="note")
router.register(
    r"memory/session-embeddings",
    viewsets.SessionEmbeddingViewSet,
    basename="session-embedding",
)
router.register(r"system-state", viewsets.SystemStateViewSet, basename="system-state")
router.register(r"dream-logs", viewsets.DreamLogViewSet, basename="dream-log")


urlpatterns = [
    # ---- public ----------------------------------------------------------
    path("health/", views.health, name="api-health"),
    path("doctor/", doctor.doctor_view, name="api-doctor"),

    # ---- auth ------------------------------------------------------------
    path("auth/login/", auth.login_view, name="api-auth-login"),
    path("auth/logout/", auth.logout_view, name="api-auth-logout"),
    path("auth/me/", auth.me_view, name="api-auth-me"),

    # ---- aggregate / search ---------------------------------------------
    path("metrics/", viewsets.metrics_view, name="api-metrics"),
    path("memory/search/", viewsets.similarity_search_view, name="api-memory-search"),

    # ---- google account management --------------------------------------
    path("google/accounts/", google.list_google_accounts, name="api-google-list"),
    path(
        "google/accounts/callback/",
        google.google_oauth_callback,
        name="api-google-callback",
    ),
    path(
        "google/accounts/<str:label>/connect/",
        google.connect_google_account,
        name="api-google-connect",
    ),
    path(
        "google/accounts/<str:label>/",
        google.disconnect_google_account,
        name="api-google-disconnect",
    ),

    # ---- model CRUD via router ------------------------------------------
    path("", include(router.urls)),
]
