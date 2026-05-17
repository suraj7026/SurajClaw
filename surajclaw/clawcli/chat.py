"""Async WebSocket REPL for ``surajclaw chat``.

The CLI is a thin client: it opens a WebSocket against the existing
``ws/chat/<session_uuid>/`` consumer and renders the streamed frames
through :class:`FrameRenderer`. All slash-command and directive parsing
happens server-side in ``chat/commands.py`` and ``chat/directives.py``,
so plain text typed at the prompt is forwarded verbatim.

Ctrl-C handling:
    * At the prompt, Ctrl-C exits the CLI cleanly.
    * Mid-turn (while frames are streaming), Ctrl-C sends ``/stop`` and
      keeps reading frames until the server emits ``done``. A second
      Ctrl-C while waiting for ``done`` aborts the connection.
"""
from __future__ import annotations

import asyncio
import json
import signal
import time
from urllib.parse import urlencode

import websockets
from rich.console import Console

from clawcli.config import http_to_ws, new_session_id
from clawcli.render import FrameRenderer

# How long to wait for the initial server `system` greeting before
# returning control to the user. Anything longer suggests the WS auth
# was rejected and we never got a frame.
_INITIAL_GREETING_TIMEOUT = 1.5

# Print a "still working" heartbeat after this many seconds of silence
# during a turn. Reset whenever a frame arrives. Keeps obvious-hang
# diagnosis trivial (the operator can see whether the agent is stuck or
# just waiting on a slow Gemini call / tool round-trip).
_HEARTBEAT_INTERVAL = 5.0


class ChatConnectionError(RuntimeError):
    """Raised when the WS handshake fails (auth rejected, server down)."""


def run_chat_repl(
    *,
    server: str,
    token: str | None,
    as_id: str | None,
    session_id: str | None,
    console: Console | None = None,
    debug: bool = False,
) -> int:
    """Synchronous entrypoint used by :mod:`clawcli.main`.

    Returns a process exit code (0 on clean exit, non-zero on error).
    """
    return asyncio.run(
        _run(
            server=server,
            token=token,
            as_id=as_id,
            session_id=session_id or new_session_id(),
            console=console or Console(),
            debug=debug,
        )
    )


async def _run(
    *,
    server: str,
    token: str | None,
    as_id: str | None,
    session_id: str,
    console: Console,
    debug: bool,
) -> int:
    ws_url = _build_ws_url(server=server, session_id=session_id, token=token, as_id=as_id)
    renderer = FrameRenderer(console=console)

    console.print(f"[dim]session={session_id}[/]")
    console.print(f"[dim]server={server}[/]")
    console.print(
        "[dim]type a message and press enter; /help for slash commands; "
        "Ctrl-C aborts a turn; Ctrl-D exits[/]"
    )

    try:
        connection = await websockets.connect(ws_url, max_size=2**22)
    except (
        websockets.InvalidStatus,
        websockets.InvalidStatusCode,  # type: ignore[attr-defined]
        websockets.InvalidHandshake,
        OSError,
    ) as exc:
        console.print(f"[bold red]connection failed:[/] {exc}")
        return 2

    async with connection as ws:
        # Drain the initial server greeting (`system: connected as ...`).
        await _drain_initial(ws, renderer)

        while True:
            try:
                message = await asyncio.to_thread(_prompt)
            except (EOFError, KeyboardInterrupt):
                console.print()
                break

            if not message or not message.strip():
                continue

            renderer.begin_user_turn(message.rstrip())
            try:
                await ws.send(json.dumps({"message": message}))
            except websockets.ConnectionClosed:
                console.print("[bold red]connection closed by server[/]")
                return 1

            ok = await _drain_until_done(ws, renderer, debug=debug)
            if not ok:
                return 1

    return 0


def _prompt() -> str:
    """Read a single line from stdin. Raises EOFError on Ctrl-D."""
    try:
        return input("> ")
    except EOFError:
        raise


def _build_ws_url(*, server: str, session_id: str, token: str | None, as_id: str | None) -> str:
    base = http_to_ws(server)
    params: dict[str, str] = {}
    if token:
        params["token"] = token
    if as_id:
        params["as"] = as_id
    query = ("?" + urlencode(params)) if params else ""
    return f"{base.rstrip('/')}/ws/chat/{session_id}/{query}"


async def _drain_initial(ws: websockets.WebSocketClientProtocol, renderer: FrameRenderer) -> None:
    try:
        raw = await asyncio.wait_for(ws.recv(), timeout=_INITIAL_GREETING_TIMEOUT)
    except (asyncio.TimeoutError, TimeoutError):
        return
    except websockets.ConnectionClosed:
        return
    try:
        frame = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return
    renderer.render(frame)


async def _drain_until_done(
    ws: websockets.WebSocketClientProtocol,
    renderer: FrameRenderer,
    *,
    debug: bool = False,
) -> bool:
    """Read frames until we see ``{"type": "done"}``.

    Returns True on a clean turn, False on connection failure.

    Emits a ``(still working ... Ns)`` heartbeat every
    :data:`_HEARTBEAT_INTERVAL` seconds of WS silence so a slow Gemini
    call or pending tool round-trip is not mistaken for a frozen CLI.
    With ``debug=True`` every received frame's ``type`` is logged.
    """
    loop = asyncio.get_running_loop()
    sigint_event = asyncio.Event()
    handler_installed = False
    try:
        loop.add_signal_handler(signal.SIGINT, sigint_event.set)
        handler_installed = True
    except (NotImplementedError, RuntimeError):
        # Signals not supported on this platform (Windows) — fall back
        # to default behavior (Ctrl-C will raise KeyboardInterrupt).
        pass

    sent_stop = False
    turn_started = time.monotonic()
    last_frame_at = turn_started
    # `websockets` allows only one concurrent recv() per connection, and
    # likewise we want one outstanding signal-wait, so we keep these
    # tasks alive across iterations and only recreate the one(s) that
    # complete each loop.
    recv_task: asyncio.Task | None = None
    sigint_task: asyncio.Task | None = None
    try:
        while True:
            if recv_task is None:
                recv_task = asyncio.create_task(ws.recv())
            if sigint_task is None:
                sigint_task = asyncio.create_task(sigint_event.wait())

            try:
                done, _pending = await asyncio.wait(
                    {recv_task, sigint_task},
                    return_when=asyncio.FIRST_COMPLETED,
                    timeout=_HEARTBEAT_INTERVAL,
                )
            except asyncio.CancelledError:
                recv_task.cancel()
                sigint_task.cancel()
                raise

            if not done:
                idle = time.monotonic() - last_frame_at
                elapsed = time.monotonic() - turn_started
                renderer.console.print(
                    f"[dim](still working... {elapsed:0.0f}s elapsed, "
                    f"{idle:0.0f}s since last frame)[/]"
                )
                continue

            if sigint_task in done:
                sigint_event.clear()
                sigint_task = None
                if not sent_stop:
                    sent_stop = True
                    renderer.console.print("[dim](sending /stop)[/]")
                    try:
                        await ws.send(json.dumps({"message": "/stop"}))
                    except websockets.ConnectionClosed:
                        if recv_task and not recv_task.done():
                            recv_task.cancel()
                        return False
                    # Keep waiting for `done` after the abort.
                    continue
                # Second Ctrl-C — abandon the turn.
                renderer.console.print("[dim](abort)[/]")
                if recv_task and not recv_task.done():
                    recv_task.cancel()
                return False

            if recv_task in done:
                try:
                    raw = recv_task.result()
                except websockets.ConnectionClosed:
                    renderer.console.print("[bold red]connection closed[/]")
                    if sigint_task and not sigint_task.done():
                        sigint_task.cancel()
                    return False
                recv_task = None
                last_frame_at = time.monotonic()
                try:
                    frame = json.loads(raw)
                except (TypeError, json.JSONDecodeError):
                    continue
                if debug:
                    renderer.console.print(
                        f"[dim cyan]frame:[/] {frame.get('type')!r} "
                        f"keys={sorted(frame.keys())}"
                    )
                renderer.render(frame)
                if frame.get("type") == "done":
                    if sigint_task and not sigint_task.done():
                        sigint_task.cancel()
                    return True
    finally:
        if recv_task and not recv_task.done():
            recv_task.cancel()
        if sigint_task and not sigint_task.done():
            sigint_task.cancel()
        if handler_installed:
            try:
                loop.remove_signal_handler(signal.SIGINT)
            except (NotImplementedError, RuntimeError):
                pass
