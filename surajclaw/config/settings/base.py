"""Base Django settings shared across environments.

Environment-specific settings (development, production) import from this file
and override only what they need.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# SURAJCLAW_ROOT/surajclaw/config/settings/base.py -> SURAJCLAW_ROOT/surajclaw
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Load .env from project root (one level above BASE_DIR, i.e. SurajClaw/)
load_dotenv(BASE_DIR.parent / ".env")

SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "insecure-dev-key-change-me-in-production",
)
DEBUG = False
ALLOWED_HOSTS: list[str] = []

# ---------------------------------------------------------------------------
# Application definition
# ---------------------------------------------------------------------------
DJANGO_APPS = [
    "daphne",  # must come before django.contrib.staticfiles
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework.authtoken",
    "corsheaders",
    "django_filters",
    "channels",
    "django_celery_beat",
    "pgvector.django",
]

LOCAL_APPS = [
    "core",
    "memory",
    "feeds",
    "custom_tools",
    "approval",
    "chat",
    "api",
    "webhooks",
    "scheduler",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # CorsMiddleware must come before CommonMiddleware so it can short-circuit
    # CORS preflight (OPTIONS) requests before any other processing happens.
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
ASGI_APPLICATION = "config.asgi.application"
WSGI_APPLICATION = None  # ASGI-only deployment

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# ---------------------------------------------------------------------------
# Database (PostgreSQL + pgvector)
# ---------------------------------------------------------------------------
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "surajclaw"),
        "USER": os.environ.get("POSTGRES_USER", "surajclaw"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", "surajclaw"),
        "HOST": os.environ.get("POSTGRES_HOST", "127.0.0.1"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
        "CONN_MAX_AGE": 60,
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Password validation
# ---------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------------------
# Internationalization
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = os.environ.get("TIME_ZONE", "UTC")
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static files
# ---------------------------------------------------------------------------
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

# ---------------------------------------------------------------------------
# Channels (WebSockets) + Redis
# ---------------------------------------------------------------------------
REDIS_HOST = os.environ.get("REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
REDIS_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}/0"

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [(REDIS_HOST, REDIS_PORT)],
        },
    },
}

# ---------------------------------------------------------------------------
# Celery
# ---------------------------------------------------------------------------
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"

# ---------------------------------------------------------------------------
# Django REST Framework
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.TokenAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.LimitOffsetPagination",
    "PAGE_SIZE": 50,
}

# ---------------------------------------------------------------------------
# Agent / LLM configuration
# ---------------------------------------------------------------------------
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "gemma4:e2b")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-1.5-pro")

EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "nomic-embed-text")
EMBEDDING_DIMENSIONS = int(os.environ.get("EMBEDDING_DIMENSIONS", "768"))

# ---------------------------------------------------------------------------
# Workspace & paths (used by file / notes tools)
# ---------------------------------------------------------------------------
WORKSPACE_DIR = Path(
    os.environ.get("WORKSPACE_DIR", str(BASE_DIR.parent / "workspace"))
)
NOTES_DIR = Path(os.environ.get("NOTES_DIR", str(BASE_DIR / "notes")))

# ---------------------------------------------------------------------------
# Google Workspace
# ---------------------------------------------------------------------------
GOOGLE_CLIENT_SECRETS_PATH = os.environ.get(
    "GOOGLE_CLIENT_SECRETS_PATH",
    str(BASE_DIR.parent / "client_secret.json"),
)
GOOGLE_TOKEN_PATH = os.environ.get(
    "GOOGLE_TOKEN_PATH",
    str(BASE_DIR.parent / "google_token.json"),
)
# Multi-account: each connected Google account gets its own `<label>.json` in
# this directory. `GOOGLE_TOKEN_PATH` above is kept as a backward-compat
# single-account fallback that we expose as the "default" account.
GOOGLE_TOKEN_DIR = os.environ.get(
    "GOOGLE_TOKEN_DIR",
    str(BASE_DIR.parent / "google_tokens"),
)
GOOGLE_SEARCH_API_KEY = os.environ.get("GOOGLE_SEARCH_API_KEY", "")
GOOGLE_SEARCH_CX = os.environ.get("GOOGLE_SEARCH_CX", "")

# Where to bounce the operator after a Google OAuth web flow finishes. The
# `/integrations` page on the React UI reads `?google=ok&label=...` to show
# a toast. Override per-environment if the dashboard isn't served at root.
FRONTEND_INTEGRATIONS_URL = os.environ.get(
    "FRONTEND_INTEGRATIONS_URL", "/integrations"
)

# ---------------------------------------------------------------------------
# Telegram / notifications
# ---------------------------------------------------------------------------
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_WEBHOOK_SECRET = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")
TELEGRAM_OWNER_ID = os.environ.get("TELEGRAM_OWNER_ID", "")

# ---------------------------------------------------------------------------
# Owner allowlist (adapted from OpenClaw's commands.allowFrom)
# ---------------------------------------------------------------------------
# Comma-separated list of authorized senders. Each entry is either a bare
# id (`123456`) applied globally, or a `channel:id` qualifier
# (`telegram:123456,web:user@example.com`). `*` is a wildcard.
OWNER_ALLOW_FROM = os.environ.get("OWNER_ALLOW_FROM", "")

# ---------------------------------------------------------------------------
# Gmail Pub/Sub watch
# ---------------------------------------------------------------------------
# Full topic name that the gmail-watch-renew Celery task re-registers daily.
# Format: projects/<project-id>/topics/<topic-name>
GMAIL_PUBSUB_TOPIC = os.environ.get("GMAIL_PUBSUB_TOPIC", "")
# JSON array of label ids to watch; defaults to ["INBOX"] when blank.
GMAIL_LABEL_IDS = os.environ.get("GMAIL_LABEL_IDS", "")

# ---------------------------------------------------------------------------
# Dream system
# ---------------------------------------------------------------------------
DREAM_MIN_SESSIONS = int(os.environ.get("DREAM_MIN_SESSIONS", "5"))
DREAM_MIN_HOURS = int(os.environ.get("DREAM_MIN_HOURS", "4"))
MAX_SUBAGENTS = int(os.environ.get("MAX_SUBAGENTS", "4"))
