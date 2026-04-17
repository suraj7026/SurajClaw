"""Idempotently install the pgvector extension on the configured DB.

We need this for the remote Postgres path: the local pgvector/pgvector image
ships the extension pre-installed, but a stock Postgres install needs both
the OS package (`postgresql-16-pgvector`) and `CREATE EXTENSION vector;`.

Run after pointing POSTGRES_HOST at a fresh DB and BEFORE `migrate`:

    python manage.py ensure_pgvector
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import connection


class Command(BaseCommand):
    help = "CREATE EXTENSION IF NOT EXISTS vector on the default DB."

    def handle(self, *_args, **_opts) -> None:
        with connection.cursor() as cur:
            try:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            except Exception as exc:  # noqa: BLE001 -- surface the actual error
                raise CommandError(
                    "Could not CREATE EXTENSION vector. Ensure the pgvector "
                    "package is installed server-side, e.g. on Ubuntu:\n"
                    "  sudo apt install postgresql-16-pgvector\n"
                    f"Original error: {exc}"
                ) from exc
            cur.execute("SELECT extname, extversion FROM pg_extension WHERE extname='vector';")
            row = cur.fetchone()
        if not row:
            raise CommandError("pgvector did not register; check Postgres logs.")
        self.stdout.write(self.style.SUCCESS(f"pgvector ready: {row[0]} v{row[1]}"))
