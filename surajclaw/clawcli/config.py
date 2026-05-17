"""CLI configuration: server URL discovery, credential storage, session ids.

Credentials live in ``~/.config/surajclaw/credentials.json`` (chmod 600). The
file holds the most recent successful login: ``{server, token, username}``.

Server URL precedence (highest first):
    1. Explicit ``--server`` flag passed on the command line.
    2. ``SURAJCLAW_SERVER`` environment variable.
    3. The ``server`` field in stored credentials.
    4. Fallback: ``http://127.0.0.1:8000``.
"""
from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse, urlunparse

DEFAULT_SERVER = "http://127.0.0.1:8000"
ENV_SERVER = "SURAJCLAW_SERVER"


def credentials_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "surajclaw" / "credentials.json"


@dataclass
class Credentials:
    server: str
    token: str
    username: str

    def as_dict(self) -> dict[str, str]:
        return {"server": self.server, "token": self.token, "username": self.username}


def load_credentials() -> Credentials | None:
    path = credentials_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    server = data.get("server")
    token = data.get("token")
    username = data.get("username") or ""
    if not server or not token:
        return None
    return Credentials(server=server, token=token, username=username)


def save_credentials(creds: Credentials) -> Path:
    path = credentials_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(creds.as_dict(), indent=2))
    # Tighten perms; best-effort on platforms that don't honour chmod.
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path


def clear_credentials() -> bool:
    path = credentials_path()
    if not path.exists():
        return False
    try:
        path.unlink()
        return True
    except OSError:
        return False


def resolve_server(explicit: str | None) -> str:
    """Resolve the server base URL using the precedence above."""
    if explicit:
        return _normalize(explicit)
    env = os.environ.get(ENV_SERVER)
    if env:
        return _normalize(env)
    creds = load_credentials()
    if creds and creds.server:
        return _normalize(creds.server)
    return DEFAULT_SERVER


def _normalize(url: str) -> str:
    """Strip trailing slashes; default scheme to http if missing."""
    url = url.strip().rstrip("/")
    if "://" not in url:
        url = f"http://{url}"
    return url


def http_to_ws(http_url: str) -> str:
    """Convert ``http(s)://host[:port]`` to ``ws(s)://host[:port]``."""
    parsed = urlparse(http_url)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    return urlunparse((scheme, parsed.netloc, parsed.path, "", "", ""))


def new_session_id() -> str:
    return str(uuid.uuid4())
