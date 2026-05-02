"""Sandbox safety policies."""
from __future__ import annotations


BLOCKED_SNIPPETS = (
    "/var/run/docker.sock",
    "--privileged",
    "--network host",
    "--pid host",
    "--ipc host",
)


def validate_command(script: str) -> tuple[bool, str]:
    for snippet in BLOCKED_SNIPPETS:
        if snippet in script:
            return False, f"blocked unsafe sandbox command snippet: {snippet}"
    return True, ""
