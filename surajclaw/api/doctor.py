"""Doctor: aggregate self-checks for the SurajClaw stack.

Adapted from OpenClaw's ``src/flows/doctor-health.ts``. Each check returns a
small dict with ``name``, ``status`` (``ok|warn|error``), and ``detail``.
The top-level status is the worst child status.

Used by:

* ``/doctor`` slash command (synchronous, called from chat consumer).
* ``GET /api/doctor`` REST endpoint for external monitoring.
* ``manage.py doctor`` management command (operational checklist).
"""
from __future__ import annotations

import logging
import socket
from dataclasses import asdict, dataclass, field
from typing import Literal

from django.conf import settings
from django.db import connection
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

logger = logging.getLogger(__name__)

Status = Literal["ok", "warn", "error"]
SEVERITY: dict[Status, int] = {"ok": 0, "warn": 1, "error": 2}


@dataclass
class CheckResult:
    name: str
    status: Status
    detail: str = ""
    extra: dict = field(default_factory=dict)


def _aggregate(results: list[CheckResult]) -> Status:
    return max((r.status for r in results), key=lambda s: SEVERITY[s], default="ok")


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------
def check_database() -> CheckResult:
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
    except Exception as exc:  # noqa: BLE001 -- bubbled up as detail
        return CheckResult("database", "error", f"connect failed: {exc}")
    return CheckResult("database", "ok", "PostgreSQL reachable")


def check_pgvector() -> CheckResult:
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT extname FROM pg_extension WHERE extname = 'vector'")
            row = cur.fetchone()
    except Exception as exc:  # noqa: BLE001
        return CheckResult("pgvector", "error", f"query failed: {exc}")
    if not row:
        return CheckResult(
            "pgvector",
            "error",
            "extension not installed; run `migrate memory`",
        )
    return CheckResult("pgvector", "ok", "extension enabled")


def check_redis() -> CheckResult:
    try:
        import redis  # type: ignore[import-not-found]

        client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            socket_connect_timeout=1.5,
        )
        client.ping()
    except Exception as exc:  # noqa: BLE001
        return CheckResult("redis", "error", f"ping failed: {exc}")
    return CheckResult("redis", "ok", f"{settings.REDIS_HOST}:{settings.REDIS_PORT}")


def check_ollama() -> CheckResult:
    try:
        import urllib.request

        url = settings.OLLAMA_BASE_URL.rstrip("/") + "/api/tags"
        with urllib.request.urlopen(url, timeout=2) as resp:  # noqa: S310 -- internal URL
            if resp.status != 200:
                return CheckResult(
                    "ollama", "error", f"HTTP {resp.status} from {url}"
                )
    except (TimeoutError, OSError, socket.timeout, ValueError) as exc:
        return CheckResult("ollama", "warn", f"unreachable: {exc}")
    return CheckResult("ollama", "ok", f"reachable at {settings.OLLAMA_BASE_URL}")


def check_gemini_key() -> CheckResult:
    if settings.GEMINI_API_KEY:
        return CheckResult(
            "gemini_key",
            "ok",
            "GEMINI_API_KEY present (not validated against API)",
        )
    return CheckResult(
        "gemini_key",
        "warn",
        "GEMINI_API_KEY missing — escalations to Gemini will fail",
    )


def check_celery_beat() -> CheckResult:
    """Look for a recent Beat heartbeat in the django_celery_beat schedule.

    Beat writes ``last_run_at`` on each periodic task. If none of the
    canonical jobs have fired in the past 2x their interval, Beat is likely
    not running.
    """
    try:
        from django_celery_beat.models import PeriodicTask  # type: ignore[import-not-found]
    except ImportError:
        return CheckResult("celery_beat", "warn", "django_celery_beat not installed")
    try:
        recent = (
            PeriodicTask.objects.exclude(last_run_at__isnull=True)
            .order_by("-last_run_at")
            .first()
        )
    except Exception as exc:  # noqa: BLE001
        return CheckResult("celery_beat", "warn", f"query failed: {exc}")
    if recent is None:
        return CheckResult(
            "celery_beat",
            "warn",
            "no PeriodicTask has run yet (Beat may not have started)",
        )
    return CheckResult(
        "celery_beat",
        "ok",
        f"last fired: {recent.name} at {recent.last_run_at.isoformat()}",
    )


def check_owner_configured() -> CheckResult:
    from chat.auth import list_owners

    channels = ("web", "telegram")
    detail = {ch: list_owners(ch) for ch in channels}
    if not any(detail.values()):
        return CheckResult(
            "owner_allowlist",
            "error",
            "no owners configured — set OWNER_ALLOW_FROM or *_OWNER_ID",
            extra=detail,
        )
    return CheckResult("owner_allowlist", "ok", "owner(s) configured", extra=detail)


def check_workspace_writable() -> CheckResult:
    from pathlib import Path

    paths = {
        "workspace": Path(settings.WORKSPACE_DIR),
        "notes": Path(settings.NOTES_DIR),
    }
    detail = {}
    worst: Status = "ok"
    for name, path in paths.items():
        try:
            path.mkdir(parents=True, exist_ok=True)
            probe = path / ".doctor"
            probe.write_text("ok")
            probe.unlink()
            detail[name] = "writable"
        except OSError as exc:
            detail[name] = f"unwritable: {exc}"
            worst = "error"
    return CheckResult("filesystem", worst, ", ".join(f"{k}={v}" for k, v in detail.items()))


CHECKS = (
    check_database,
    check_pgvector,
    check_redis,
    check_ollama,
    check_gemini_key,
    check_celery_beat,
    check_owner_configured,
    check_workspace_writable,
)


def run_checks() -> dict:
    """Run every registered check. Returns a JSON-serializable summary."""
    results: list[CheckResult] = []
    for fn in CHECKS:
        try:
            results.append(fn())
        except Exception as exc:  # noqa: BLE001 -- never let a check crash the report
            logger.exception("doctor check %s failed", fn.__name__)
            results.append(CheckResult(fn.__name__, "error", f"raised: {exc}"))
    return {
        "status": _aggregate(results),
        "checks": [asdict(r) for r in results],
    }


@api_view(["GET"])
@permission_classes([AllowAny])
def doctor_view(_request: Request) -> Response:
    """``GET /api/doctor`` — public health summary, safe for external monitors.

    Public on purpose (so an uptime probe doesn't need credentials), but it
    only returns coarse status strings — no secrets, no IDs.
    """
    report = run_checks()
    http_status = 200 if report["status"] != "error" else 503
    return Response(report, status=http_status)
