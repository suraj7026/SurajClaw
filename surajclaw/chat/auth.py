"""Owner allowlist + command authorization.

Adapted from OpenClaw's `src/auto-reply/command-auth.ts` and
`src/channels/allow-from.ts`. Single-user assistant: enforce that only the
configured owner can drive the agent, regardless of which channel the
message arrived on (web chat, Telegram, GitHub webhook, etc.).

Two policies are merged:

* `OWNER_ALLOW_FROM` (env, comma-separated) — global owners. Each entry can
  be a bare id (`123456`) or a `channel:id` qualifier
  (`telegram:123456`, `web:user@example.com`). `*` is a wildcard.
* Per-channel envs already in settings, e.g. `TELEGRAM_OWNER_ID`, used as a
  fallback when `OWNER_ALLOW_FROM` does not list the channel explicitly.

The whole point is that webhook handlers and the chat consumer call one
function — `is_owner(channel, sender_id)` — and that function reads policy
once, caches it, and applies it deterministically.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from functools import lru_cache

from django.conf import settings

logger = logging.getLogger(__name__)


WILDCARD = "*"


@dataclass(frozen=True)
class OwnerPolicy:
    """Resolved allowlist for a single channel.

    ``entries`` are normalized lowercase strings without the channel prefix.
    ``has_wildcard`` short-circuits to "anyone allowed" only when the
    wildcard was explicit; an empty allowlist is *deny*, not allow.
    """

    channel: str
    entries: frozenset[str] = field(default_factory=frozenset)
    has_wildcard: bool = False

    @property
    def has_entries(self) -> bool:
        return self.has_wildcard or bool(self.entries)


def _parse_allow_from(raw: str) -> dict[str, set[str]]:
    """Parse comma-separated allowlist into ``{channel: {ids...}}``.

    ``*`` (no channel prefix) becomes the global wildcard for every channel.
    ``telegram:*`` is a wildcard scoped to one channel only.
    """
    out: dict[str, set[str]] = {}
    for raw_entry in (raw or "").split(","):
        entry = raw_entry.strip()
        if not entry:
            continue
        if ":" in entry:
            channel, _, value = entry.partition(":")
            channel = channel.strip().lower()
            value = value.strip()
            if not channel or not value:
                continue
            out.setdefault(channel, set()).add(value.lower())
        else:
            out.setdefault(WILDCARD, set()).add(entry.lower())
    return out


@lru_cache(maxsize=None)
def _resolve_policy(channel: str) -> OwnerPolicy:
    """Build the effective allowlist for ``channel`` (e.g. ``"telegram"``).

    Cached because the env-driven config is immutable for the process
    lifetime. Tests should call ``reset_policy_cache()`` if they mutate
    settings.
    """
    channel = (channel or "").strip().lower()
    parsed = _parse_allow_from(getattr(settings, "OWNER_ALLOW_FROM", ""))
    raw_entries: set[str] = set()

    # Global ids without channel scope apply to every channel.
    raw_entries.update(parsed.get(WILDCARD, set()))
    # Channel-specific ids.
    raw_entries.update(parsed.get(channel, set()))

    # Per-channel fallback envs from existing settings. Keep this list short;
    # add new channels here as we wire them up rather than scanning settings.
    fallbacks = {
        "telegram": getattr(settings, "TELEGRAM_OWNER_ID", "") or "",
    }
    fallback = fallbacks.get(channel, "").strip().lower()
    if fallback:
        raw_entries.add(fallback)

    has_wildcard = WILDCARD in raw_entries
    entries = frozenset(e for e in raw_entries if e and e != WILDCARD)
    return OwnerPolicy(channel=channel, entries=entries, has_wildcard=has_wildcard)


def reset_policy_cache() -> None:
    """Clear cached policies. Call from tests after settings overrides."""
    _resolve_policy.cache_clear()


def is_owner(channel: str, sender_id: str | int | None) -> bool:
    """Return True if ``sender_id`` is on the allowlist for ``channel``.

    Two sources are merged (DB first, env second):

    1. ``pairing.ApprovedSender`` rows (added at runtime via the pairing flow).
    2. ``settings.OWNER_ALLOW_FROM`` + per-channel fallback envs.

    A *missing* allowlist (no DB row, no env entry, no wildcard) returns
    False -- single-user assistant fails closed. Set ``OWNER_ALLOW_FROM=*``
    if you want a public demo.
    """
    # 1. Runtime pairing DB takes precedence so the operator can grant
    # access without redeploying.
    try:
        from pairing.services import is_approved

        if sender_id is not None and is_approved(channel, sender_id):
            return True
    except Exception as exc:  # noqa: BLE001 -- pairing app might not be migrated yet
        logger.debug("pairing lookup failed: %s", exc)

    # 2. Env-based allowlist (legacy + bootstrap path).
    policy = _resolve_policy(channel)
    if not policy.has_entries:
        logger.warning(
            "auth: no owner configured for channel=%s; denying. "
            "Set OWNER_ALLOW_FROM, %s_OWNER_ID, or pair a sender via "
            "`python manage.py pair`.",
            channel,
            channel.upper(),
        )
        return False
    if policy.has_wildcard:
        return True
    if sender_id is None:
        return False
    return str(sender_id).strip().lower() in policy.entries


def assert_owner(channel: str, sender_id: str | int | None) -> None:
    """Raise PermissionDenied if the sender is not on the allowlist."""
    from django.core.exceptions import PermissionDenied

    if not is_owner(channel, sender_id):
        raise PermissionDenied(f"sender {sender_id!r} not authorized on {channel}")


def list_owners(channel: str) -> list[str]:
    """Return the sorted, lowercased allowlist for diagnostics (`/status`)."""
    policy = _resolve_policy(channel)
    base = sorted(policy.entries)
    if policy.has_wildcard:
        return ["*", *base]
    return base
