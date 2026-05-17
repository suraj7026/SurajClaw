# clawcli — SurajClaw CLI

This package is the operator surface for SurajClaw. It is **not** a Django
app: no `apps.py`, no models, no migrations. It is a standalone Python
package wired up as a console script via `surajclaw/pyproject.toml`.

## Layout

- `main.py` — `argparse` dispatcher. Subcommands: `login`, `logout`,
  `whoami`, `doctor`, `status`, `chat`, `tui`. Each subcommand resolves
  to a `_cmd_*` handler that returns an int exit code. `chat` and `tui`
  share auth + server resolution via `_resolve_chat_auth`.
- `config.py` — credential storage (`~/.config/surajclaw/credentials.json`,
  chmod 600), server-URL precedence (`--server` > `SURAJCLAW_SERVER` env >
  stored creds > `http://127.0.0.1:8000`), `http_to_ws` helper, session-id
  generator.
- `http.py` — thin `httpx.Client` wrapper. Injects
  `Authorization: Token <key>`. All non-2xx responses raise
  `ApiError` so callers print a clean error line.
- `chat.py` — async WebSocket REPL (line-based). Connects to
  `ws/chat/<session_uuid>/?token=…` (or `?as=<name>` with `--no-auth`),
  reads stdin via `asyncio.to_thread(input, …)`, races each WS recv
  against a SIGINT `asyncio.Event` so Ctrl-C mid-turn sends `/stop` and a
  second Ctrl-C abandons the turn. Prints a `(still working… Ns)`
  heartbeat after `_HEARTBEAT_INTERVAL` seconds of silence. `--debug`
  logs every received frame's `type`/keys.
- `render.py` — `FrameRenderer` maps server frame `type`s
  (`token`, `tool_call`, `tool_result`, `node_update`, `command_result`,
  `system`, `error`, `final`, `done`) to terminal output via `rich`. If
  no `token` frames stream during a turn, the `final` content is rendered
  in full (covers the non-streaming model case).
- `tui.py` — full-screen Textual app (`SurajclawTui`). Sidebar shows
  session id, server, and a quick command/directive cheatsheet. Main
  pane is a `RichLog` for committed history plus a separate `Static`
  for the in-progress assistant text (tokens accumulate in
  `_streaming_buffer` and the buffer is flushed to the RichLog on any
  non-token frame or `done`). Heartbeat lives on a one-line status
  widget; key bindings: `ctrl+d` quit, `ctrl+l` clear,
  `ctrl+s` send `/stop`, `ctrl+n` new session, `ctrl+r` reconnect.

## Wiring contract

The CLI is a thin client. Slash commands and inline directives live
**server-side**:

- `chat/commands.py` — `/help`, `/status`, `/stop`, `/agents`, `/agent`,
  `/approve`, `/deny`, `/doctor`, `/notes`, `/model`. Add new ones there.
- `chat/directives.py` — `!model`, `!thinking`, `!tools`. Add new ones
  there.
- `chat/consumers.py::ChatConsumer` — entry point. Owns owner-allowlist
  gating, per-session turn lock (`turn_task`), and the
  `register_session_notifier` hook that lets background jobs push frames
  into a live WS.
- `agents/subgraphs/reactive.py::_stream_llm` — streams Gemini chunks via
  `bound.stream(composed)` and emits `{"type": "token", "agent":<id>,
  "content": <chunk>}` frames on the consumer-supplied `on_event`. If
  the bound runnable lacks `.stream()`, falls back to `.invoke()`.

Do **not** re-implement any of this in `clawcli/`. If the CLI needs a new
behavior (e.g. cancel a turn from outside the REPL), prefer adding a
slash command + REST endpoint and call it from `main.py`.

## Conventions

- Frame `type` values are an open enum. Always render unknown types
  verbatim (`_render_unknown` in the REPL, "(unknown frame)" branch in
  the TUI) so we surface new server features without silently dropping
  them.
- Never decode the user message before sending — the server decides
  what is a slash command, what is a directive, and what is plain text.
  The CLI just forwards `{"message": "<raw>"}`.
- Server URL resolution must go through `config.resolve_server`. Do not
  re-implement precedence elsewhere.
- Credential file writes go through `config.save_credentials` so
  permissions stay at 600.

## Testing

There is no automated test suite. Smoke tests:

- `surajclaw --help` and each subcommand `--help` should render.
- `surajclaw login` against a local Daphne (`make dev`).
- `surajclaw doctor` and `surajclaw status` should respond.
- `surajclaw chat`: send "hello", expect a `token` stream then `final`
  then `done`. Try `/agents` and `/stop` mid-turn.
- `surajclaw tui`: launch, type a message, watch tokens stream into the
  in-progress widget, then commit on `final`. `ctrl+s` aborts mid-turn.
