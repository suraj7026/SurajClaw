"""``python manage.py doctor`` — operational checklist.

Same checks as the ``/api/doctor`` HTTP endpoint, but rendered for a
terminal: colored status, exit code matching overall status (0 = ok/warn,
2 = error). Useful in deploy scripts:

    python manage.py doctor || exit 1
"""
from __future__ import annotations

from django.core.management.base import BaseCommand

from api.doctor import run_checks

_GLYPH = {"ok": "OK ", "warn": "WARN", "error": "ERR "}


class Command(BaseCommand):
    help = "Run SurajClaw self-checks (DB, Redis, Ollama, Gemini, pgvector, owners)."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--json",
            action="store_true",
            help="Emit machine-readable JSON instead of a table.",
        )

    def handle(self, *_args, **opts) -> None:
        report = run_checks()
        if opts["json"]:
            import json

            self.stdout.write(json.dumps(report, indent=2))
        else:
            for check in report["checks"]:
                glyph = _GLYPH.get(check["status"], "??  ")
                self.stdout.write(f"  [{glyph}] {check['name']:<20} {check['detail']}")
            self.stdout.write(f"\noverall: {report['status']}")
        if report["status"] == "error":
            raise SystemExit(2)
