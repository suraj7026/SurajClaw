"""In-process WebSocket notification registry.

Chat turns now run inline from the active WebSocket connection, so normal token
streaming uses a per-turn callback. Approval prompts can still be raised from
deep inside tool execution, so this module keeps a tiny session keyed registry
for best-effort direct delivery in the single-process local deployment.
"""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from asgiref.sync import async_to_sync

logger = logging.getLogger(__name__)

Notifier = Callable[[dict[str, Any]], Awaitable[None]]

_NOTIFIERS: dict[str, Notifier] = {}


def register_session_notifier(session_id: str, notifier: Notifier) -> None:
    _NOTIFIERS[str(session_id)] = notifier


def unregister_session_notifier(session_id: str, notifier: Notifier | None = None) -> None:
    key = str(session_id)
    _NOTIFIERS.pop(key, None)


def notify_session(session_id: str, payload: dict[str, Any]) -> bool:
    notifier = _NOTIFIERS.get(str(session_id))
    if notifier is None:
        return False
    try:
        async_to_sync(notifier)(payload)
    except Exception as exc:  # noqa: BLE001 -- notification failure should not kill tools
        logger.warning("websocket notify failed for session %s: %s", session_id, exc)
        return False
    return True
