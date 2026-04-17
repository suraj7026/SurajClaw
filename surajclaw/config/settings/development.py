"""Development settings: DEBUG on, relaxed hosts, verbose logging."""
from __future__ import annotations

from .base import *  # noqa: F401, F403

DEBUG = True

ALLOWED_HOSTS = ["*"]

INTERNAL_IPS = ["127.0.0.1"]

# CORS — wide-open in dev so the Vite dev server (default port 5173) and
# any local tooling can hit the API without origin checks. Production
# settings should switch to an explicit `CORS_ALLOWED_ORIGINS` list.
CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True

# CSRF — accept cross-origin POSTs from the dev frontend.
CSRF_TRUSTED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{asctime}] {levelname} {name}: {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "agents": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": False,
        },
        "tools": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": False,
        },
    },
}
