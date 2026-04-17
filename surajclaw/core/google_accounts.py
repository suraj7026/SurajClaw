"""Helpers for managing multiple Google Workspace OAuth accounts.

Each connected account has a file ``{GOOGLE_TOKEN_DIR}/{label}.json`` holding
the authorized_user credentials produced by ``google_oauth_login``. The label
is a short slug you pick (``personal``, ``work``, ...).

For backward compatibility, if ``GOOGLE_TOKEN_PATH`` points at an existing
file and the token directory is empty, we also surface it as the
``default`` account.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from django.conf import settings

# Lowercase letters, digits, dash, underscore. Keeps filenames portable and
# safe to splice into logs/CLI output.
LABEL_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")


@dataclass(frozen=True)
class GoogleAccount:
    """One row in the ``google_tokens/`` directory."""

    label: str
    token_path: Path

    def load_credentials(self, scopes: list[str] | None = None):
        """Return ``google.oauth2.credentials.Credentials`` for this account.

        ``scopes`` is passed through to ``from_authorized_user_info``. Most
        callers leave it ``None`` because the token file already records the
        granted scopes.
        """
        # Import lazily so missing google libs don't break non-Google flows.
        from google.oauth2.credentials import Credentials  # type: ignore[import-not-found]

        data = json.loads(self.token_path.read_text(encoding="utf-8"))
        return Credentials.from_authorized_user_info(data, scopes=scopes)


def token_dir() -> Path:
    """Return the configured token directory, creating it on demand."""
    path = Path(settings.GOOGLE_TOKEN_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


def validate_label(label: str) -> str:
    """Raise ``ValueError`` if ``label`` isn't a safe filename slug."""
    if not LABEL_RE.match(label):
        raise ValueError(
            f"account label {label!r} must be lowercase [a-z0-9_-], "
            "1-32 chars, not starting with a dash/underscore"
        )
    return label


def path_for(label: str) -> Path:
    """Return ``google_tokens/<label>.json`` — does *not* check existence."""
    return token_dir() / f"{validate_label(label)}.json"


def list_accounts() -> list[GoogleAccount]:
    """Return all known accounts, sorted by label.

    Deterministic ordering keeps prompt caches and log lines stable across
    runs — we rely on this from the watcher loop below.
    """
    accounts: dict[str, GoogleAccount] = {}
    for f in sorted(token_dir().glob("*.json")):
        label = f.stem
        if not LABEL_RE.match(label):
            continue  # Skip anything that doesn't match the safe slug shape.
        accounts[label] = GoogleAccount(label=label, token_path=f)

    # Back-compat: surface the legacy single-file token as the "default"
    # account when nothing else is configured.
    legacy = Path(getattr(settings, "GOOGLE_TOKEN_PATH", "") or "")
    if not accounts and legacy.exists():
        accounts["default"] = GoogleAccount(label="default", token_path=legacy)
    return list(accounts.values())


def iter_accounts() -> Iterator[GoogleAccount]:
    yield from list_accounts()


def get_account(label: str) -> GoogleAccount:
    """Return a single account by label or raise ``LookupError``."""
    p = path_for(label)
    if not p.exists():
        raise LookupError(
            f"no token for account {label!r} at {p}. "
            f"Run: python manage.py google_oauth_login --account {label}"
        )
    return GoogleAccount(label=label, token_path=p)
