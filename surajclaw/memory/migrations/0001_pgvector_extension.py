"""Enable the pgvector PostgreSQL extension.

This migration must run before any VectorField-backed tables are created,
so we keep it as the first migration in the `memory` app with no model
dependencies of its own. The `CREATE EXTENSION` requires superuser
privileges or a role with the `CREATEROLE` + `rds_superuser` equivalent
depending on the host; on self-hosted PostgreSQL the application user
usually needs to be granted this once during provisioning.
"""
from __future__ import annotations

from pgvector.django import VectorExtension
from django.db import migrations


class Migration(migrations.Migration):
    initial = True

    dependencies: list[tuple[str, str]] = []

    operations = [
        VectorExtension(),
    ]
