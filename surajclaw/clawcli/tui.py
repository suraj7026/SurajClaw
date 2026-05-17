"""Textual-based TUI for ``surajclaw tui``.

Layout:

    +-------------+----------------------------------------+
    | sidebar     | chat history (RichLog, scrollable)     |
    |  session    |                                        |
    |  server     |                                        |
    |  commands   |                                        |
    |             |                                        |
    |             | streaming assistant text (live)        |
    |             | status (spinner + node + elapsed)      |
    |             | input box                              |
    +-------------+----------------------------------------+
    | footer (key bindings)                                |
    +------------------------------------------------------+

The TUI talks to the same WebSocket endpoint as ``surajclaw chat``
(``/ws/chat/<session_uuid>/``). All slash commands and inline
directives are forwarded verbatim and dispatched server-side; the TUI
only renders frames.

Key bindings:

* ``ctrl+d``   exit
* ``ctrl+l``   clear chat history
* ``ctrl+s``   send ``/stop`` (abort the current turn)
* ``ctrl+n``   start a new session (reconnects with a fresh UUID)
* ``ctrl+r``   reconnect (same session)
* ``ctrl+m``   open model picker
* ``ctrl+h``   open session history
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any
from urllib.parse import urlencode

import websockets
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.suggester import Suggester
from textual.widgets import Footer, Header, Input, RichLog, Static

from clawcli.config import http_to_ws, new_session_id

_PREVIEW_LIMIT = 240
_HEARTBEAT_TICK = 0.15  # faster tick for smooth spinner
_BRAILLE = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

_SLASH_COMMANDS = [
    "/help",
    "/agents",
    "/agent",
    "/model",
    "/google",
    "/stop",
    "/doctor",
    "/notes",
    "/memory",
    "/clear",
]

_DIRECTIVES = [
    "!model gemini-3.1-flash-lite",
    "!model gemini-3-flash",
    "!model gemini-3.1-pro-preview",
    "!model gemini-3.1-flash-live-preview",
    "!model gemini-2.5-flash-lite",
    "!model gemini-2.5-flash",
    "!model gemini-2.5-pro",
    "!model gemini-2.0-flash",
    "!thinking on",
    "!thinking off",
    "!thinking budget=8192",
]


class CommandSuggester(Suggester):
    """Autocomplete for /commands and !directives."""

    async def get_suggestion(self, value: str) -> str | None:
        if not value:
            return None
        candidates = _SLASH_COMMANDS if value.startswith("/") else _DIRECTIVES if value.startswith("!") else []
        for candidate in candidates:
            if candidate.startswith(value) and candidate != value:
                return candidate
        return None


def run_tui(
    *,
    server: str,
    token: str | None,
    as_id: str | None,
    session_id: str | None,
    debug: bool = False,
) -> int:
    """Synchronous entrypoint used by :mod:`clawcli.main`.

    Returns 0 on clean exit.
    """
    app = SurajclawTui(
        server=server,
        token=token,
        as_id=as_id,
        session_id=session_id or new_session_id(),
        debug=debug,
    )
    app.run()
    return 0


class SurajclawTui(App):
    """Textual chat client for the SurajClaw backend."""

    CSS = """
    Screen { background: $surface; }

    #sidebar {
        width: 28;
        padding: 1 1 0 2;
        border-right: solid $accent-darken-2;
    }
    #sidebar .label { color: $text-muted; text-style: bold; }
    #sidebar .value { color: $text; padding-bottom: 1; }
    #sidebar .hint  { color: $text-muted; padding-bottom: 0; }

    #main { padding: 0 1 0 1; }

    #chat {
        height: 1fr;
        border: round $accent-darken-2;
        padding: 0 1;
    }

    #streaming {
        height: auto;
        max-height: 20;
        padding: 0 1;
        color: $text;
    }

    #status {
        height: 1;
        padding: 0 1;
        color: $accent;
        text-style: bold;
    }

    #activity {
        height: auto;
        max-height: 10;
        padding: 0 1;
        color: $text-muted;
    }

    #input {
        dock: bottom;
        margin: 0 1 0 1;
    }
    """

    BINDINGS = [
        Binding("ctrl+d", "quit", "Quit", priority=True),
        Binding("ctrl+l", "clear", "Clear"),
        Binding("ctrl+s", "stop", "Stop turn"),
        Binding("ctrl+n", "new_session", "New session"),
        Binding("ctrl+r", "reconnect", "Reconnect"),
        Binding("ctrl+m", "model_picker", "Model"),
        Binding("ctrl+h", "session_picker", "Sessions"),
        Binding("ctrl+g", "google_accounts", "Google"),
    ]

    TITLE = "surajclaw"

    def __init__(
        self,
        *,
        server: str,
        token: str | None,
        as_id: str | None,
        session_id: str,
        debug: bool = False,
    ) -> None:
        super().__init__()
        self.server = server
        self.token = token
        self.as_id = as_id
        self.session_id = session_id
        self._debug = debug

        self._ws: websockets.WebSocketClientProtocol | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._heartbeat_task: asyncio.Task[None] | None = None

        # Per-turn state.
        self._turn_active = False
        self._turn_started_at = 0.0
        self._last_frame_at = 0.0
        self._spinner_tick = 0
        # Whether the current turn streamed any token frames. Used to skip
        # re-rendering the `final` frame for streaming models (the content
        # is already in the chat log via `_commit_streaming`).
        self._turn_had_tokens = False

        # Buffer of in-progress assistant text.  Tokens accumulate here
        # and the `#streaming` widget re-renders.  On any non-token frame
        # (or `done`) we commit the buffer to the RichLog as markdown.
        self._streaming_buffer = ""

        # Tool trail. ``_pending_tool_calls`` holds in-flight calls waiting on
        # a result frame; ``_completed_tools`` holds finished calls until the
        # AI starts streaming a post-tool response — at which point we erase
        # them (the Claude-Code-CLI pattern). Neither is logged to the chat
        # log; both render only inside the live activity widget.
        self._pending_tool_calls: list[dict[str, Any]] = []
        self._completed_tools: list[dict[str, Any]] = []

        # Name of the currently active agent node (from node_update frames).
        self._current_node = ""

        self.sub_title = session_id

    # ---- compose --------------------------------------------------------
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal():
            with Vertical(id="sidebar"):
                yield Static("session", classes="label")
                yield Static(self.session_id, classes="value", id="session-value")
                yield Static("server", classes="label")
                yield Static(self.server, classes="value")
                yield Static("you", classes="label")
                yield Static(self._identity_label(), classes="value")
                yield Static("commands", classes="label")
                yield Static("/help    list commands", classes="hint")
                yield Static("/agents  list agents", classes="hint")
                yield Static("/agent   invoke agent", classes="hint")
                yield Static("/model   pick model", classes="hint")
                yield Static("/google  google accounts", classes="hint")
                yield Static("/stop    abort turn", classes="hint")
                yield Static("/doctor  health", classes="hint")
                yield Static("/notes   recent notes", classes="hint")
                yield Static("", classes="hint")
                yield Static("directives", classes="label")
                yield Static("!model gemini ...", classes="hint")
                yield Static("!thinking ...", classes="hint")
            with Vertical(id="main"):
                yield RichLog(
                    id="chat",
                    wrap=True,
                    markup=False,
                    highlight=False,
                    auto_scroll=True,
                )
                yield Static("", id="streaming")
                yield Static("", id="activity")
                yield Static("", id="status")
                yield Input(
                    placeholder="Type a message — /help for commands. ctrl+d quits.",
                    id="input",
                    suggester=CommandSuggester(use_cache=False),
                )
        yield Footer()

    # ---- lifecycle ------------------------------------------------------
    async def on_mount(self) -> None:
        self.query_one("#input", Input).focus()
        self._log_dim(f"session={self.session_id}")
        self._log_dim(f"server={self.server}")
        await self._connect()

    async def on_unmount(self) -> None:
        await self._disconnect()

    # ---- connection management -----------------------------------------
    async def _connect(self) -> None:
        ws_url = self._build_ws_url()
        self._log_dim("connecting...")
        try:
            self._ws = await websockets.connect(ws_url, max_size=2**22)
        except Exception as exc:  # noqa: BLE001 -- surface as text
            self._log_error(f"connection failed: {exc}")
            return
        self._reader_task = asyncio.create_task(self._read_loop())

    async def _disconnect(self) -> None:
        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:  # noqa: BLE001
                pass
        self._ws = None
        self._reader_task = None
        self._heartbeat_task = None

    def _build_ws_url(self) -> str:
        base = http_to_ws(self.server)
        params: dict[str, str] = {}
        if self.token:
            params["token"] = self.token
        if self.as_id:
            params["as"] = self.as_id
        query = ("?" + urlencode(params)) if params else ""
        return f"{base.rstrip('/')}/ws/chat/{self.session_id}/{query}"

    def _identity_label(self) -> str:
        if self.token:
            return "(token auth)"
        if self.as_id:
            return f"as={self.as_id}"
        return "(unauthenticated)"

    # ---- input handler --------------------------------------------------
    async def on_input_submitted(self, event: Input.Submitted) -> None:
        message = event.value.strip()
        if not message:
            return
        event.input.value = ""

        # `/model` and `/models` open the picker locally instead of being
        # sent to the server, since the server doesn't have a /model
        # command and the directive (!model X) takes a model name.
        if message in {"/model", "/models"}:
            await self.action_model_picker()
            return
        if message in {"/google", "/accounts"}:
            await self.action_google_accounts()
            return
        if self._ws is None:
            self._log_error("not connected; press ctrl+r to reconnect")
            return
        if self._turn_active:
            self._log_dim(
                "(a turn is already running — type /stop or press ctrl+s to abort)"
            )
            return

        self._log(
            Panel(
                Text(message, overflow="fold", no_wrap=False),
                title="[bold cyan]▎you",
                title_align="left",
                border_style="cyan",
                padding=(0, 1),
                width=self._panel_width(),
            )
        )
        try:
            await self._ws.send(json.dumps({"message": message}))
        except (websockets.ConnectionClosed, OSError) as exc:
            self._log_error(f"send failed: {exc}")
            return

        self._begin_turn()

    # ---- frame handling -------------------------------------------------
    async def _read_loop(self) -> None:
        ws = self._ws
        if ws is None:
            return
        try:
            async for raw in ws:
                try:
                    frame = json.loads(raw)
                except (TypeError, json.JSONDecodeError):
                    continue
                self._last_frame_at = time.monotonic()
                if self._debug:
                    self._log_dim(
                        f"frame: {frame.get('type')!r} keys={sorted(frame.keys())}"
                    )
                self._render_frame(frame)
        except asyncio.CancelledError:
            raise
        except websockets.ConnectionClosed:
            self._log_error("connection closed")
            self._end_turn()
        except Exception as exc:  # noqa: BLE001
            self._log_error(f"read loop error: {exc}")
            self._end_turn()

    def _render_frame(self, frame: dict[str, Any]) -> None:
        ftype = frame.get("type")
        if ftype == "token":
            content = frame.get("content")
            if isinstance(content, str) and content:
                # First token of a fresh streaming batch *after* one or more
                # tools have completed → that's the AI's post-tool answer.
                # Wipe the completed-tool entries from the activity widget,
                # like Claude Code CLI does, so the final response is the
                # focus.
                if (
                    not self._streaming_buffer
                    and self._completed_tools
                    and not self._pending_tool_calls
                ):
                    self._completed_tools = []
                    self._refresh_activity()
                self._streaming_buffer += content
                self._turn_had_tokens = True
                self._refresh_streaming()
            return

        # Non-token frame: commit any in-progress streaming text first.
        self._commit_streaming()

        if ftype == "tool_call":
            name = frame.get("name") or "<tool>"
            args = frame.get("args") or {}
            agent = frame.get("agent") or self._current_node or ""
            self._pending_tool_calls.append(
                {"name": name, "args": args, "started": time.monotonic(), "agent": agent}
            )
            self._refresh_activity()
        elif ftype == "tool_result":
            name = frame.get("name") or "<tool>"
            content = frame.get("content")
            if not isinstance(content, str):
                try:
                    content = json.dumps(content, default=str)
                except (TypeError, ValueError):
                    content = str(content)
            preview = content.replace("\n", " ").strip()
            if len(preview) > 100:
                preview = preview[:100] + "..."
            # Match against the oldest pending call with the same name.
            call: dict[str, Any] | None = None
            for i, pending in enumerate(self._pending_tool_calls):
                if pending["name"] == name:
                    call = self._pending_tool_calls.pop(i)
                    break
            self._completed_tools.append(
                {
                    "name": name,
                    "agent": (call or {}).get("agent", "")
                    or frame.get("agent")
                    or self._current_node
                    or "",
                    "elapsed": time.monotonic() - call["started"] if call else 0.0,
                    "preview": preview,
                }
            )
            self._refresh_activity()
        elif ftype == "node_entered":
            # Track the active node for the live activity strip / status
            # line, but DO NOT log it to the chat log — the user wants a
            # clean transcript of just |you and |surajclaw exchanges.
            self._current_node = frame.get("node") or "?"
            self._refresh_activity()
        elif ftype == "node_update":
            self._current_node = frame.get("node") or "?"
        elif ftype == "command_result":
            self._log(
                Panel(
                    Text(str(frame.get("content") or ""), overflow="fold", no_wrap=False),
                    title="[bold]▎command",
                    title_align="left",
                    border_style="blue",
                    padding=(0, 1),
                    width=self._panel_width(),
                )
            )
        elif ftype == "system":
            self._log(Text(f"(system) {frame.get('content') or ''}", style="italic dim"))
        elif ftype == "error":
            self._log(
                Panel(
                    Text(
                        str(frame.get("content") or "(unknown error)"),
                        overflow="fold",
                        no_wrap=False,
                    ),
                    title="[bold red]▎error",
                    title_align="left",
                    border_style="red",
                    padding=(0, 1),
                    width=self._panel_width(),
                )
            )
        elif ftype == "approval":
            asyncio.create_task(self._handle_approval(frame))
        elif ftype == "final":
            # Only render the final content for non-streaming models that
            # never emitted token frames. For streaming models the content
            # is already in the chat log via _commit_streaming, so a second
            # render would duplicate it under the magenta panel.
            content = frame.get("content")
            if not self._turn_had_tokens and content:
                log = self.query_one("#chat", RichLog)
                log.write(
                    Panel(
                        Text(str(content), overflow="fold", no_wrap=False),
                        title="[bold magenta]▎surajclaw",
                        title_align="left",
                        border_style="magenta",
                        padding=(0, 1),
                        width=self._panel_width(log),
                    )
                )
        elif ftype == "done":
            self._end_turn()
        else:
            self._log(Text(f"(unknown frame) {frame}", style="dim"))

    # ---- tool trail -----------------------------------------------------
    def _format_tool_panel(self, result_frame: dict[str, Any]) -> Panel:
        """Render a paired tool call + result as a single bordered panel."""
        name = result_frame.get("name") or "<tool>"
        content = result_frame.get("content")
        if not isinstance(content, str):
            try:
                content = json.dumps(content, default=str)
            except (TypeError, ValueError):
                content = str(content)

        # Match against the oldest pending call with the same name.
        call: dict[str, Any] | None = None
        for i, pending in enumerate(self._pending_tool_calls):
            if pending["name"] == name:
                call = self._pending_tool_calls.pop(i)
                break

        elapsed_str = ""
        args_text = ""
        if call:
            elapsed_str = f" [{time.monotonic() - call['started']:.1f}s]"
            try:
                args_text = json.dumps(call["args"], default=str)
            except (TypeError, ValueError):
                args_text = str(call["args"])
            if len(args_text) > 400:
                args_text = args_text[:400] + "..."

        result_preview = content.strip()
        if len(result_preview) > 1000:
            result_preview = result_preview[:1000] + "...(truncated)"

        body = Text()
        if args_text:
            body.append("args: ", style="dim")
            body.append(f"{args_text}\n\n", style="yellow")
        body.append("result:\n", style="dim")
        body.append(result_preview, style="green")

        agent_part = ""
        if call and call.get("agent"):
            agent_part = f" [dim]· {call['agent']}[/dim]"
        return Panel(
            body,
            title=f"[bold yellow]▎{name}[/bold yellow]{agent_part}[dim]{elapsed_str}[/dim]",
            title_align="left",
            border_style="yellow",
            padding=(0, 1),
        )

    # ---- approval gate -------------------------------------------------
    async def _handle_approval(self, frame: dict[str, Any]) -> None:
        from clawcli.http import ApiClient
        from clawcli.modals import ApprovalModal

        request_id = frame.get("request_id") or ""
        description = frame.get("description") or "Approve this action?"

        async def on_decision(decision: str | None) -> None:
            resolved = decision or "rejected"
            self._log_dim(f"(approval {resolved}: {description[:60]})")
            if not request_id:
                return
            try:
                client = ApiClient(server=self.server, token=self.token)
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    None,
                    lambda: client.post(
                        f"/approval/{request_id}/respond/",
                        {"decision": resolved, "responded_by": "tui"},
                    ),
                )
            except Exception as exc:  # noqa: BLE001
                self._log_error(f"approval respond failed: {exc}")

        await self.push_screen(ApprovalModal(request_id=request_id, description=description), on_decision)

    # ---- turn lifecycle -------------------------------------------------
    def _begin_turn(self) -> None:
        self._turn_active = True
        self._turn_started_at = time.monotonic()
        self._last_frame_at = self._turn_started_at
        self._streaming_buffer = ""
        self._pending_tool_calls = []
        self._completed_tools = []
        self._current_node = ""
        self._spinner_tick = 0
        self._turn_had_tokens = False
        self._refresh_streaming()
        if self._heartbeat_task is None or self._heartbeat_task.done():
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    def _end_turn(self) -> None:
        self._turn_active = False
        if self._heartbeat_task is not None and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
        self._heartbeat_task = None
        # Flush any tool calls that never got a result frame.
        for pending in self._pending_tool_calls:
            out = Text()
            out.append("▸ ", style="dim yellow")
            out.append(pending["name"], style="dim")
            out.append("  (no result frame received)", style="dim italic")
            self._log(out)
        self._pending_tool_calls = []
        self._completed_tools = []
        self._current_node = ""
        self._commit_streaming()
        self._set_status("")
        self._refresh_activity()

    async def _heartbeat_loop(self) -> None:
        try:
            while self._turn_active:
                elapsed = time.monotonic() - self._turn_started_at
                idle = time.monotonic() - self._last_frame_at
                spinner = _BRAILLE[self._spinner_tick % len(_BRAILLE)]
                self._spinner_tick += 1
                node_part = f" [{self._current_node}]" if self._current_node else ""
                self._set_status(
                    f"{spinner}{node_part}  {elapsed:.0f}s elapsed "
                    f"({idle:.0f}s idle)  ctrl+s to /stop"
                )
                # Keep the running-tool strip animated.
                self._refresh_activity()
                await asyncio.sleep(_HEARTBEAT_TICK)
        except asyncio.CancelledError:
            pass

    # ---- streaming buffer -----------------------------------------------
    def _refresh_streaming(self) -> None:
        widget = self.query_one("#streaming", Static)
        if not self._streaming_buffer:
            widget.update("")
            return
        widget.update(
            Panel(
                Text(self._streaming_buffer, overflow="fold", no_wrap=False),
                title="[bold magenta]▎surajclaw is typing...",
                title_align="left",
                border_style="magenta",
                padding=(0, 1),
            )
        )

    def _refresh_activity(self) -> None:
        """Live tool / agent status — cleared when post-tool response starts."""
        widget = self.query_one("#activity", Static)
        spinner = _BRAILLE[self._spinner_tick % len(_BRAILLE)]
        lines: list[Text] = []
        if self._turn_active and self._current_node:
            head = Text()
            head.append(f"{spinner} ", style="bold blue")
            head.append("active: ", style="dim")
            head.append(self._current_node, style="bold blue")
            lines.append(head)
        for tool in self._completed_tools[-4:]:
            row = Text()
            row.append("  ✓ ", style="bold green")
            row.append(tool["name"], style="green")
            if tool.get("agent"):
                row.append(f" · {tool['agent']}", style="dim")
            row.append(f"  {tool['elapsed']:.1f}s", style="dim")
            if tool.get("preview"):
                row.append(f"  → {tool['preview']}", style="dim")
            lines.append(row)
        for call in self._pending_tool_calls[-3:]:
            elapsed = time.monotonic() - call["started"]
            row = Text()
            row.append(f"  {spinner} ", style="bold yellow")
            row.append("running ", style="dim")
            row.append(call["name"], style="bold yellow")
            agent = call.get("agent")
            if agent:
                row.append(f" · {agent}", style="dim")
            row.append(f"  {elapsed:.0f}s", style="dim")
            lines.append(row)
        if not lines:
            widget.update("")
            return
        combined = lines[0]
        for r in lines[1:]:
            combined = combined + Text("\n") + r
        widget.update(combined)

    def _commit_streaming(self) -> None:
        if not self._streaming_buffer:
            return
        log = self.query_one("#chat", RichLog)
        node = (self._current_node or "").lower()
        title = (
            "[bold magenta]▎surajclaw"
            if node in {"", "ai", "general"}
            else f"[bold magenta]▎surajclaw [/bold magenta][dim]· {node}[/dim]"
        )
        log.write(
            Panel(
                Text(self._streaming_buffer, overflow="fold", no_wrap=False),
                title=title,
                title_align="left",
                border_style="magenta",
                padding=(0, 1),
                width=self._panel_width(log),
            )
        )
        self._streaming_buffer = ""
        self._refresh_streaming()

    # ---- chat-log helpers -----------------------------------------------
    def _panel_width(self, log: RichLog | None = None) -> int:
        """Interior width Panels should render at to wrap correctly.

        Rich's ``Panel`` doesn't auto-discover the available width when
        rendered through Textual's ``RichLog.write`` — the inner Text
        then never wraps and gets visually clipped at the right border.
        Passing a known width to Panel forces the Text inside to wrap.
        """
        if log is None:
            log = self.query_one("#chat", RichLog)
        # ``scrollable_content_region.width`` is the interior of the
        # widget (after its own border + padding). Subtract a couple of
        # cells so we never overflow into the scrollbar area.
        try:
            width = log.scrollable_content_region.width - 2
        except Exception:  # noqa: BLE001 -- be defensive about Textual internals
            width = log.size.width - 4 if log.size.width else 80
        return max(20, width)

    def _log(self, content: Text | str) -> None:
        self.query_one("#chat", RichLog).write(content)

    def _log_dim(self, text: str) -> None:
        self._log(Text(text, style="dim"))

    def _log_error(self, text: str) -> None:
        self._log(Text(text, style="bold red"))

    def _set_status(self, text: str) -> None:
        widget = self.query_one("#status", Static)
        widget.update(Text(text, style="dim") if text else "")

    # ---- actions (key bindings) ----------------------------------------
    def action_clear(self) -> None:
        self.query_one("#chat", RichLog).clear()
        self._streaming_buffer = ""
        self._refresh_streaming()
        self._set_status("")

    async def action_stop(self) -> None:
        if self._ws is None:
            return
        if not self._turn_active:
            self._log_dim("(no turn in progress)")
            return
        try:
            await self._ws.send(json.dumps({"message": "/stop"}))
            self._log_dim("(sent /stop)")
        except (websockets.ConnectionClosed, OSError) as exc:
            self._log_error(f"send /stop failed: {exc}")

    async def action_new_session(self) -> None:
        await self._disconnect()
        self.session_id = new_session_id()
        self.sub_title = self.session_id
        try:
            self.query_one("#session-value", Static).update(self.session_id)
        except Exception:  # noqa: BLE001
            pass
        self._streaming_buffer = ""
        self._pending_tool_calls = []
        self._completed_tools = []
        self._current_node = ""
        self._refresh_streaming()
        self._set_status("")
        self._log_dim(f"--- new session: {self.session_id} ---")
        await self._connect()

    async def action_reconnect(self) -> None:
        await self._disconnect()
        self._streaming_buffer = ""
        self._pending_tool_calls = []
        self._completed_tools = []
        self._current_node = ""
        self._refresh_streaming()
        self._set_status("")
        self._log_dim("--- reconnecting ---")
        await self._connect()

    async def action_model_picker(self) -> None:
        from clawcli.modals import ModelPickerModal

        async def on_select(model: str | None) -> None:
            if model and self._ws:
                try:
                    await self._ws.send(json.dumps({"message": f"!model {model}"}))
                    self._log_dim(f"(model → {model})")
                except (websockets.ConnectionClosed, OSError):
                    pass

        await self.push_screen(ModelPickerModal(), on_select)

    async def action_session_picker(self) -> None:
        from clawcli.modals import SessionPickerModal

        async def on_select(session_id: str | None) -> None:
            if not session_id or session_id == self.session_id:
                return
            await self._disconnect()
            self.session_id = session_id
            self.sub_title = session_id
            try:
                self.query_one("#session-value", Static).update(session_id)
            except Exception:  # noqa: BLE001
                pass
            self._streaming_buffer = ""
            self._pending_tool_calls = []
            self._completed_tools = []
            self._current_node = ""
            self._refresh_streaming()
            self._set_status("")
            self._log_dim(f"--- resumed session: {session_id} ---")
            await self._connect()

        await self.push_screen(
            SessionPickerModal(server=self.server, token=self.token),
            on_select,
        )

    async def action_google_accounts(self) -> None:
        from clawcli.modals import GoogleAccountsModal

        async def on_change(_: object | None) -> None:
            self._log_dim("(google accounts updated — re-ask the agent to use them)")

        await self.push_screen(
            GoogleAccountsModal(server=self.server, token=self.token),
            on_change,
        )
