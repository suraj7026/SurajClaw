"""WebSocket consumer for live chat.

Chat turns run inline from the active WebSocket connection. The agent receives
a direct streaming callback and Celery is reserved for scheduled/background
jobs.

Inbound messages flow through three preflight stages, in order:

1. **Owner allowlist** — :func:`chat.auth.is_owner`. Anonymous WS clients
   without an authenticated Django user are rejected unless the policy
   explicitly grants ``web:*``.
2. **Slash command** — :func:`chat.commands.detect`. Control-plane commands
   (``/help``, ``/status``, ``/stop``, ``/approve``, etc.) run synchronously
   and never reach the LLM.
3. **Inline directives** — :func:`chat.directives.parse` strips
    ``!model gemini`` style overrides and forwards the cleaned message plus
    the parsed overrides into the inline agent turn.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any
from urllib.parse import parse_qs

from asgiref.sync import sync_to_async
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from chat.auth import is_owner
from chat.commands import (
    CommandContext,
    detect as detect_command,
    dispatch as dispatch_command,
)
from chat.directives import parse as parse_directives
from chat.streaming import register_session_notifier, unregister_session_notifier

logger = logging.getLogger(__name__)


class ChatConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self) -> None:
        self.session_id = str(self.scope["url_route"]["kwargs"]["session_id"])
        # Cache per-connection identity so receive_json doesn't recompute.
        self.sender_id, self.is_authenticated_user = await self._identity_from_scope()
        self.is_owner = self.is_authenticated_user or is_owner("web", self.sender_id)
        self.turn_task: asyncio.Task | None = None
        if not self.is_owner:
            logger.warning(
                "rejecting WS connect: sender=%r not on web allowlist",
                self.sender_id,
            )
            await self.close(code=4403)
            return
        await self.accept()
        register_session_notifier(self.session_id, self._send_stream_event)
        await self.send(
            text_data=json.dumps(
                {"type": "system", "content": f"connected as {self.sender_id}"}
            )
        )

    async def disconnect(self, code: int) -> None:
        if self.turn_task and not self.turn_task.done():
            self.turn_task.cancel()
        unregister_session_notifier(self.session_id, self._send_stream_event)

    async def receive_json(self, content: dict[str, Any], **_: Any) -> None:
        message = (content.get("message") or "").strip()
        if not message:
            return
        logger.info(
            "chat message received: session=%s sender=%s length=%s",
            self.session_id,
            self.sender_id,
            len(message),
        )

        # Slash command? Run synchronously, return result, do not call LLM.
        match = detect_command(message)
        if match is not None:
            ctx = CommandContext(
                session_id=self.session_id,
                sender_id=self.sender_id,
                channel="web",
                args=match.args,
                is_owner=self.is_owner,
            )
            result = await sync_to_async(dispatch_command, thread_sensitive=True)(match, ctx)
            await self.send(
                text_data=json.dumps({"type": "command_result", "content": result.text})
            )
            if result.abort_turn and self.turn_task and not self.turn_task.done():
                self.turn_task.cancel()
            await self.send(text_data=json.dumps({"type": "done"}))
            return

        # Strip leading !directives before dispatching to the agent.
        directives, body = parse_directives(message)
        if not body:
            await self.send(
                text_data=json.dumps(
                    {"type": "command_result", "content": "(directives only — no message body)"}
                )
            )
            await self.send(text_data=json.dumps({"type": "done"}))
            return

        if self.turn_task and not self.turn_task.done():
            await self.send_json(
                {"type": "system", "content": "An agent turn is already running. Use /stop to cancel it."}
            )
            await self.send_json({"type": "done"})
            return

        self.turn_task = asyncio.create_task(
            self._run_agent_turn(
                body,
                {
                    "model": directives.model,
                    "thinking": directives.thinking,
                    "tools_allow": directives.tools_allow,
                },
            )
        )

    async def _run_agent_turn(self, body: str, directives: dict[str, Any]) -> None:
        from agents.graph import run_turn

        loop = asyncio.get_running_loop()

        # `run_turn` runs inside a worker thread (sync_to_async). It calls
        # `on_event` synchronously from there, so we shuttle each frame
        # back to the consumer's event loop via `call_soon_threadsafe`.
        # That keeps `self.send_json` on the right loop without blocking
        # the agent thread on every token.
        def on_event(payload: dict[str, Any]) -> None:
            loop.call_soon_threadsafe(
                lambda: asyncio.ensure_future(self.send_json(payload))
            )

        try:
            await sync_to_async(run_turn, thread_sensitive=True)(
                session_id=self.session_id,
                message=body,
                source="web",
                directives=directives,
                on_event=on_event,
            )
        except asyncio.CancelledError:
            await self.send_json({"type": "system", "content": "Agent turn cancelled."})
            raise
        finally:
            await self.send_json({"type": "done"})
            self.turn_task = None

    async def _send_stream_event(self, payload: dict[str, Any]) -> None:
        await self.send_json(payload)

    # ---- helpers ---------------------------------------------------------
    async def _identity_from_scope(self) -> tuple[str | None, bool]:
        """Resolve a stable identity for the connected client.

        Order: authenticated Django session user > DRF token user > URL-supplied
        ``?as=<id>`` (handy for local CLI testing) > None. The React app logs
        in with DRF tokens, so WebSocket auth has to handle that query param.
        """
        user = self.scope.get("user")
        if user is not None and getattr(user, "is_authenticated", False):
            return getattr(user, "username", None) or getattr(user, "email", None), True

        query = self.scope.get("query_string", b"").decode("utf-8", errors="ignore")
        params = parse_qs(query)
        token = (params.get("token") or [""])[0]
        if token:
            sender = await _sender_from_token(token)
            if sender:
                return sender, True

        sender = (params.get("as") or [""])[0]
        return sender or None, False


@database_sync_to_async
def _sender_from_token(token: str) -> str | None:
    try:
        from rest_framework.authtoken.models import Token

        row = Token.objects.select_related("user").filter(key=token).first()
    except Exception as exc:  # noqa: BLE001 -- auth failure should just reject WS
        logger.debug("token lookup failed: %s", exc)
        return None
    if not row or not row.user or not row.user.is_active:
        return None
    return row.user.username or row.user.email or str(row.user_id)
