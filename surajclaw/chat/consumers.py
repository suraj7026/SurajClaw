"""WebSocket consumer for live chat.

On connect we attach the consumer to a per-session channel group so
background Celery workers (and the agent) can push tokens/approval
requests back to the browser.

Inbound messages flow through three preflight stages, in order:

1. **Owner allowlist** — :func:`chat.auth.is_owner`. Anonymous WS clients
   without an authenticated Django user are rejected unless the policy
   explicitly grants ``web:*``.
2. **Slash command** — :func:`chat.commands.detect`. Control-plane commands
   (``/help``, ``/status``, ``/stop``, ``/approve``, etc.) run synchronously
   and never reach the LLM.
3. **Inline directives** — :func:`chat.directives.parse` strips
   ``!model gemini`` style overrides and forwards the cleaned message plus
   the parsed overrides into the Celery turn.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from channels.generic.websocket import AsyncJsonWebsocketConsumer

from chat.auth import is_owner
from chat.commands import (
    CommandContext,
    detect as detect_command,
    dispatch as dispatch_command,
)
from chat.directives import parse as parse_directives

logger = logging.getLogger(__name__)


class ChatConsumer(AsyncJsonWebsocketConsumer):
    groups: list[str] = []

    async def connect(self) -> None:
        self.session_id = str(self.scope["url_route"]["kwargs"]["session_id"])
        self.group_name = f"chat.{self.session_id}"
        # Cache per-connection identity so receive_json doesn't recompute.
        self.sender_id = self._sender_id_from_scope()
        self.is_owner = is_owner("web", self.sender_id)
        if not self.is_owner:
            logger.warning(
                "rejecting WS connect: sender=%r not on web allowlist",
                self.sender_id,
            )
            await self.close(code=4403)
            return
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, code: int) -> None:
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive_json(self, content: dict[str, Any], **_: Any) -> None:
        message = (content.get("message") or "").strip()
        if not message:
            return

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
            result = dispatch_command(match, ctx)
            await self.send(
                text_data=json.dumps({"type": "command_result", "content": result.text})
            )
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

        from scheduler.tasks import run_agent_turn

        run_agent_turn.delay(
            session_id=self.session_id,
            message=body,
            source="web",
            directives={
                "model": directives.model,
                "thinking": directives.thinking,
                "tools_allow": directives.tools_allow,
            },
        )

    # ---- group event handlers (called via channel_layer.group_send) ------

    async def chat_token(self, event: dict[str, Any]) -> None:
        """Stream a single token chunk back to the client."""
        await self.send(text_data=json.dumps({"type": "token", "content": event["content"]}))

    async def chat_done(self, event: dict[str, Any]) -> None:
        await self.send(text_data=json.dumps({"type": "done"}))

    async def chat_approval(self, event: dict[str, Any]) -> None:
        await self.send(
            text_data=json.dumps(
                {
                    "type": "approval",
                    "request_id": event["request_id"],
                    "description": event["description"],
                }
            )
        )

    # ---- helpers ---------------------------------------------------------
    def _sender_id_from_scope(self) -> str | None:
        """Resolve a stable identity for the connected client.

        Order: authenticated user's username/email > URL-supplied
        ``?as=<id>`` (handy for local CLI testing) > None.
        """
        user = self.scope.get("user")
        if user is not None and getattr(user, "is_authenticated", False):
            return getattr(user, "username", None) or getattr(user, "email", None)
        query = self.scope.get("query_string", b"").decode("utf-8", errors="ignore")
        for piece in query.split("&"):
            if piece.startswith("as="):
                return piece[3:] or None
        return None
