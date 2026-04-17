"""WebSocket consumer for live chat.

On connect we attach the consumer to a per-session channel group so
background Celery workers (and the agent) can push tokens/approval
requests back to the browser. On receive we enqueue the user message
for the agent pipeline.
"""
from __future__ import annotations

import json
from typing import Any

from channels.generic.websocket import AsyncJsonWebsocketConsumer


class ChatConsumer(AsyncJsonWebsocketConsumer):
    groups: list[str] = []

    async def connect(self) -> None:
        self.session_id = str(self.scope["url_route"]["kwargs"]["session_id"])
        self.group_name = f"chat.{self.session_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, code: int) -> None:
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive_json(self, content: dict[str, Any], **_: Any) -> None:
        message = content.get("message", "")
        if not message:
            return
        # Dispatch to Celery so long-running agent work doesn't block the WS.
        from scheduler.tasks import run_agent_turn

        run_agent_turn.delay(session_id=self.session_id, message=message)

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
