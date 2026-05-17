"""Render server-streamed chat frames to the terminal using ``rich``.

The backend (`chat/consumers.py` + `agents/graph.py`) emits these frame
``type`` values, which we map to terminal output:

* ``token``           — assistant text chunk; printed inline, no newline
* ``tool_call``       — agent invoked a tool (dim arrow line)
* ``tool_result``     — tool returned (dim arrow line, content truncated)
* ``node_update``     — orchestrator graph node finished (very dim)
* ``command_result``  — slash command output (bold)
* ``system``          — server-side notice (italic)
* ``error``           — error frame (red)
* ``final``           — end-of-turn full text (we mostly use it as a marker)
* ``done``            — turn finished; caller re-prompts

Anything we don't recognise is printed verbatim so the operator can spot
new frame types without losing data.
"""
from __future__ import annotations

import json
from typing import Any

from rich.console import Console
from rich.markdown import Markdown
from rich.text import Text

_PREVIEW_LIMIT = 240


class FrameRenderer:
    """Stateful renderer: keeps track of mid-token-stream context."""

    def __init__(self, console: Console | None = None) -> None:
        self.console = console or Console()
        # Track whether we're mid-token-stream so we can insert a newline
        # before the next non-token frame.
        self._mid_stream = False
        # Track whether ANY tokens streamed during the current turn. When
        # the model doesn't stream (e.g. Gemini `generateContent`), the
        # only assistant text we see is the `final` frame, so we render
        # that content directly. Reset on `done`.
        self._turn_had_tokens = False

    # ---- public API -----------------------------------------------------
    def render(self, frame: dict[str, Any]) -> None:
        ftype = frame.get("type")
        if ftype == "token":
            self._render_token(frame)
            return
        # Anything other than a token finishes the current streaming line.
        self._flush_stream()
        if ftype == "tool_call":
            self._render_tool_call(frame)
        elif ftype == "tool_result":
            self._render_tool_result(frame)
        elif ftype == "node_update":
            self._render_node(frame)
        elif ftype == "command_result":
            self._render_command_result(frame)
        elif ftype == "system":
            self._render_system(frame)
        elif ftype == "error":
            self._render_error(frame)
        elif ftype == "final":
            self._render_final(frame)
        elif ftype == "done":
            # Reset turn-level state. Caller re-prompts; nothing to render.
            self._turn_had_tokens = False
            return
        else:
            self._render_unknown(frame)

    def begin_user_turn(self, message: str) -> None:
        self._flush_stream()
        self.console.print(Text(f"you  ", style="bold cyan") + Text(message))

    def begin_assistant_turn(self) -> None:
        self._flush_stream()
        self.console.print(Text("ai   ", style="bold magenta"), end="")
        self._turn_had_tokens = False

    # ---- internals ------------------------------------------------------
    def _render_token(self, frame: dict[str, Any]) -> None:
        content = frame.get("content")
        if not isinstance(content, str) or not content:
            return
        if not self._mid_stream:
            # Caller may not have called begin_assistant_turn() yet (e.g.
            # tokens arriving after a node_update or system). Print a thin
            # prefix so output stays readable.
            self.console.print(Text("ai   ", style="bold magenta"), end="")
        self.console.print(content, end="", soft_wrap=True, highlight=False)
        self._mid_stream = True
        self._turn_had_tokens = True

    def _flush_stream(self) -> None:
        if self._mid_stream:
            self.console.print()  # newline
            self._mid_stream = False

    def _render_tool_call(self, frame: dict[str, Any]) -> None:
        name = frame.get("name") or "<tool>"
        args = frame.get("args") or {}
        try:
            args_text = json.dumps(args, default=str, separators=(",", ":"))
        except (TypeError, ValueError):
            args_text = str(args)
        if len(args_text) > _PREVIEW_LIMIT:
            args_text = args_text[:_PREVIEW_LIMIT] + "..."
        self.console.print(
            Text("\u2192 ", style="dim yellow") + Text(f"{name}({args_text})", style="dim")
        )

    def _render_tool_result(self, frame: dict[str, Any]) -> None:
        name = frame.get("name") or "<tool>"
        content = frame.get("content")
        if not isinstance(content, str):
            try:
                content = json.dumps(content, default=str)
            except (TypeError, ValueError):
                content = str(content)
        preview = content.replace("\n", " ")
        if len(preview) > _PREVIEW_LIMIT:
            preview = preview[:_PREVIEW_LIMIT] + "..."
        self.console.print(
            Text("\u2190 ", style="dim green") + Text(f"{name}: {preview}", style="dim")
        )

    def _render_node(self, frame: dict[str, Any]) -> None:
        node = frame.get("node") or "?"
        self.console.print(Text(f"[{node}]", style="dim"))

    def _render_command_result(self, frame: dict[str, Any]) -> None:
        content = frame.get("content") or ""
        self.console.print(Text(content, style="bold"))

    def _render_system(self, frame: dict[str, Any]) -> None:
        content = frame.get("content") or ""
        self.console.print(Text(f"(system) {content}", style="italic dim"))

    def _render_error(self, frame: dict[str, Any]) -> None:
        content = frame.get("content") or "(unknown error)"
        self.console.print(Text(f"error: {content}", style="bold red"))

    def _render_final(self, frame: dict[str, Any]) -> None:
        content = frame.get("content")
        if not content:
            return
        # Models that don't stream tokens only deliver assistant text in the
        # final frame — render it as markdown so formatting is preserved.
        if not self._turn_had_tokens:
            self.console.print(Text("ai   ", style="bold magenta"))
            self.console.print(Markdown(str(content)))
        self.console.rule(style="dim")

    def _render_unknown(self, frame: dict[str, Any]) -> None:
        self.console.print(Text(f"(unknown frame) {frame}", style="dim"))
