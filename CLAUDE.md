# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Scope

Real application code lives in `surajclaw/`. The repo root holds `.env`, `start.sh`, plan files in `.claude/plans/`, and `docker-compose.yml` references. `PersonalAI_SoftwareDoc.md` is design intent — when it conflicts with code under `surajclaw/`, trust the code.

## Commands

The fastest dev path is the launcher script:

```bash
./start.sh              # postgres + daphne + celery worker + beat, streams logs
./start.sh web          # web only (skip celery)
./start.sh --install    # also pip-install requirements before booting
# Ctrl-C cleanly stops everything via the trap in start.sh
```

The Makefile is still there if you want individual services. All `make` targets run from `surajclaw/` and assume the venv is at `../.venv`:

```bash
cd surajclaw && make install     # pip install requirements.txt into ../.venv
cd surajclaw && make migrate
cd surajclaw && make dev         # daphne :8000
cd surajclaw && make celery      # worker + beat foreground
cd surajclaw && make cli         # pip install -e .  -> registers `surajclaw` console script
```

**Daily operations**

```bash
# Chat agent OAuth (Google AI Pro subscription)
python manage.py gemini_login              # browser PKCE flow, saves token
python manage.py gemini_login status       # show email + project_id + expiry
python manage.py gemini_login reonboard    # re-detect Code Assist tier after upgrading
python manage.py gemini_login logout

# Status of all OAuth flows that feed SurajClaw
python manage.py codeassist_status

# Pairing flow (replaces / augments OWNER_ALLOW_FROM)
python manage.py pair list                            # pending codes
python manage.py pair senders                         # approved devices
python manage.py pair approve <CODE> [--label "..."]
python manage.py pair deny <CODE>
python manage.py pair revoke <channel> <sender_id>

# Google Workspace inbox / calendar / tasks (separate scope set from chat OAuth)
python manage.py google_oauth_login --account personal

# Expose SurajClaw as an MCP server (stdio)
python manage.py mcp_serve

# Health
python manage.py check
python manage.py doctor

# Pgvector bootstrap (only needed if Postgres image isn't pgvector/pgvector)
python manage.py ensure_pgvector

# CLI from any shell (after `make cli`)
surajclaw login                # store DRF token for ws://.../ws/chat/
surajclaw chat                 # line-based REPL
surajclaw tui                  # Textual full-screen UI
surajclaw doctor               # remote health
```

No checked-in test suite. `make test` runs `python manage.py test` against zero discovered tests. Smoke verification: `python manage.py check`, `python manage.py codeassist_status`, then `surajclaw chat` round-trip.

## Architecture

### Model provider — OAuth only

**Every agent turn routes through OAuth-backed Google Gemini** via the Code Assist endpoint (`cloudcode-pa.googleapis.com`). There is no API-key path, no Claude, no NVIDIA NIM — those providers were intentionally removed. The OAuth credential file is `google_tokens/gemini_oauth.json`; access tokens refresh on demand.

Default model is **`gemini-2.5-flash`** (chosen for headroom against consumer-plan RPM caps). `!model gemini-2.5-pro` per-turn upgrades when you need deeper reasoning. `agents/gemini_cloudcode_chat.py::ChatGeminiCloudCode` is the only `BaseChatModel` impl wired in; it streams via SSE, retries 429s using Google's `"reset after Xs"` hint (3 attempts, 90s budget), and handles 401 by telling the operator to re-run `gemini_login`.

Memory embeddings also go through this same OAuth flow (Code Assist `embedContent`), see `memory/services.py::_embed_via_oauth`.

### Request path

```
CLI (clawcli/)             WebSocket client only — all logic is server-side
   │ ws://host/ws/chat/<uuid>/?token=<key>
   ▼
chat/consumers.py          AsyncJsonWebsocketConsumer; owner allowlist check, then
                           slash commands (chat/commands.py) → directives
                           (chat/directives.py) → agents.graph.run_turn()
   │
   ▼
agents/graph.py            Persists Message, builds AgentState, invokes orchestrator
   │
   ▼
agents/orchestrator.py     Top-level LangGraph; ALWAYS calls "general" first;
                           if GENERAL emits ROUTE: <TARGET>, delegates to that node
   │
   ├── general              -> web.search, memory.search, workspace.*, sandbox.*,
   │                          agents.spawn_subagent
   ├── google_workspace     -> google.gmail/calendar/tasks/drive/docs/sheets/contacts
   ├── code_executor        -> sandbox.*
   ├── notes                -> notes.*, web.search, workspace.write_file, memory
   ├── browser              -> mcp.playwright.* (only present if MCP_SERVERS configured)
   └── coding               -> coding.gemini_cli_run, sandbox.read_file, sandbox.run_shell
```

All specialists share `agents/subgraphs/reactive.py::build_agent_subgraph` — explicit `agent_llm` + `tool_executor` nodes, capped at `max_loops`. The shared streaming callback (`state["context"]["on_event"]`) emits typed frames (`token`, `tool_call`, `tool_result`) that the consumer forwards to the WebSocket.

### Routing semantics

GENERAL delegates by writing `ROUTE: <TARGET>` on its own line at the end of its reply. `agents/orchestrator.py::ROUTE_TARGETS` is the canonical list: `GOOGLE_WORKSPACE`, `CODE_EXECUTOR`, `NOTES`, `BROWSER`, `CODE`. Tool use and delegation are mutually exclusive in one turn.

Adding a new specialist requires three coordinated edits: `agents/registry.py` (definition + system prompt + tool allowlist), `agents/subgraphs/<id>.py` (one call to `build_agent_subgraph`), and `agents/orchestrator.py` (node + edge + ROUTE_TARGETS entry + General prompt update).

### Subagent spawning

The General Agent has a `agents.spawn_subagent` tool (see `tools/agents/spawn.py`) so it can spin up an ephemeral subagent for one-off multi-step tasks that don't fit any specialist. The subagent's allowed tools must be a subset of `SPAWNABLE_TOOLS` (workspace/sandbox/notes/web/memory — Google/browser/coding deliberately excluded). Spawning with any tool grant is approval-gated via `approval/gate.py::_dynamic_gate`.

### Tool registry

`tools/registry.py::register_tool()` is the single registration point. Every new tool module must be imported from `tools/registry.py::_ensure_builtin_tools_loaded()` (import-side-effect registration). `allowed_tools` on an `AgentDefinition` accepts either exact ids or trailing-`*` prefixes (`"mcp.playwright.*"`) — see `tools/registry.py::_agent_allows`.

`execute_tool()` is the only callsite that actually runs a tool. It enforces (in order): agent allowlist match → required env vars present → approval gate (static `GATED_TOOLS` set + `_dynamic_gate` hook for argument-dependent gating) → audit log.

### MCP integration (client + server)

**Client**: `tools/mcp/client.py` reads `settings.MCP_SERVERS` (JSON list in env), spawns each server (stdio subprocess or HTTP/SSE) via `langchain-mcp-adapters`, and registers every discovered tool as `mcp.<server_name>.<tool>`. Discovery uses a dedicated daemon-thread event loop so MCP's async API doesn't poison the rest of the sync codebase. Failures are non-fatal — missing dep or unreachable server logs a warning and skips that server.

**Server**: `surajclaw/mcp_server.py` exposes 8 SurajClaw tools (`conversations_list`, `messages_read`, `send_telegram`, `pending_approvals`, `respond_to_approval`, `memory_search`, `kanban_enqueue`, `kanban_status`) via the official `mcp` SDK (`FastMCP`, stdio). Run with `python manage.py mcp_serve` so Django apps are loaded before the server starts. Wire into other clients (Claude Code, Cursor) by pointing them at that command.

### Owner allowlist + pairing

`chat/auth.py::is_owner(channel, sender_id)` is the single auth gate. It consults two sources, **DB first**:

1. `pairing.ApprovedSender` rows (created at runtime by the pairing flow).
2. `settings.OWNER_ALLOW_FROM` (legacy bootstrap path).

The pairing flow lets a new device/sender introduce itself, receive an 8-char code (unambiguous alphabet, 1h TTL), and become trusted after the owner approves it via `manage.py pair approve <CODE>` or the WebUI. Email inbound senders automatically get a code emailed back if they're not yet approved (see `scheduler/email_poller.py::_start_pairing_email`).

### Inbound channels

| Channel | Entry point | Auth check |
|---|---|---|
| Web/CLI WebSocket | `chat/consumers.py` | `is_owner("web", username/email)` |
| Telegram webhook | `webhooks/telegram.py` → `scheduler.tasks.handle_telegram_update` | `is_owner("telegram", user_id)` |
| Email IMAP poll | `scheduler/email_poller.py` (Celery beat every 2min) | `is_owner("email", sender)`, unknown → pairing email |
| GitHub webhook | `webhooks/github.py` (stub) | n/a |
| Gmail push | `webhooks/gmail_push.py` (stub) | n/a |

### Background jobs

Celery uses **Postgres** as both broker (SQLAlchemy via `sqla+postgresql+psycopg://...`, derived from `POSTGRES_*` env when `CELERY_BROKER_URL` is blank) and result backend (`django-db`). Beat schedule lives in `config/celery.py` and includes: cron poll (30s), kanban dispatch (30s), kanban reclaim-stale (5min), email poll (2min), future-queue poll (1min), approval-expire (1min), dream-check (30min), gmail-watch renew (daily), db-backup (daily), rss-poll (30min).

**New task modules MUST be imported from `scheduler/tasks.py`** or the worker will reject them as unregistered — `autodiscover_tasks()` only walks `scheduler.tasks`.

### Cron parity (per-job overrides)

`core.CronJob` rows support `model_provider` (a `directive_model` string passed to the router) and `delivery_targets` (JSON list of `{channel, to|url}`). The runner (`scheduler/cron_runner.py`) fans delivery out to `webhook`, `telegram`, `email`, or `log` channels per row, capturing the final response into `CronRun.summary` and the delivery outcome into `CronRun.delivery_status`.

### Kanban (durable long-running work)

`kanban.KanbanTask` is a state-machine row (queued → claimed → running → done/failed). `kanban/worker.py::kanban_dispatch` claims rows with `SELECT FOR UPDATE SKIP LOCKED`, runs the agent inline, heartbeats every ~30s; `kanban_reclaim_stale` resets claims whose heartbeat is older than the per-row `stale_after_seconds`. REST endpoints under `/api/kanban/tasks/` for create/list/cancel. Survives Daphne and worker restarts.

### Approval flow + WebUI

`approval/gate.py::intercept_if_gated()` creates an `ApprovalRequest` row, notifies the active WebSocket via `chat/streaming.py::notify_session`, then polls the DB every 1.5s until the row leaves PENDING (10-minute timeout). Dashboard at `/ui/approvals/` (HTMX, 3s auto-refresh) renders the queue + approve/deny buttons. Auth reuses the DRF token + the same `is_owner("web", ...)` check used by the WebSocket. There is no React/SPA build — pure server-rendered templates in `web/templates/web/`.

### Coding agent

The only coding spawner left is `coding.gemini_cli_run` (`tools/coding/gemini_cli.py`), which `docker run`s the `surajclaw-gemini-cli:latest` image (built from `docker/gemini-cli/Dockerfile`). It mounts the host's `~/.gemini` directory into the container so the inner CLI inherits the user's Google OAuth — no API key needed. Output is structured: the container saves Gemini's JSON envelope to `/tmp/gemini-output.json`, echoes it between `===GEMINI_RESULT_START===` / `===GEMINI_RESULT_END===` sentinels, and the host-side `_extract_gemini_output` parses it back from stdout. Claude Code, Anthropic API, and NVIDIA NIM are NOT supported — do not reintroduce them; the goal is one provider, one auth flow.

The shared container plumbing lives in `tools/coding/_runner.py::run_coding_container` (clone → branch → run AI → commit → push → draft PR). New coding spawners would supply: image tag, env dict, `ai_command` bash fragment, optional `output_extractor`, optional `mounts`.

### CLI

`clawcli/` is a thin WebSocket client (no agent logic). REPL (`chat.py`) and Textual TUI (`tui.py`) share `_resolve_chat_auth` in `main.py`. Server URL resolution order: `--server` flag → stored credentials → `SURAJCLAW_SERVER` env → `http://127.0.0.1:8000`. The `surajclaw` command is registered via `pyproject.toml` after `make cli`.

## Environment

`.env` lives at the **repo root**, NOT inside `surajclaw/`. `config/settings/base.py` loads `../.env`; `docker-compose.yml` references the same path.

Required-ish:
- `DJANGO_SECRET_KEY`
- `POSTGRES_*` (host, db, user, password)
- `OWNER_ALLOW_FROM` (e.g. `web:local`)
- `GH_TOKEN` (only for the coding agent)

Optional:
- `MCP_SERVERS` (JSON list)
- `EMAIL_IMAP_*` and `SMTP_*` (for the email inbound channel)
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_OWNER_ID`
- `SURAJCLAW_GEMINI_PROJECT_ID`, `SURAJCLAW_GEMINI_TIER` (Code Assist overrides — rarely needed)
- `GEMINI_OAUTH_MODEL` (default `gemini-2.5-flash`)

OAuth credentials live in `google_tokens/` at the repo root (gitignored). The Workspace flow writes one file per `--account label`; the Gemini chat flow writes `gemini_oauth.json`.

## Key gotchas

- **OAuth-only provider model.** Don't reintroduce `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`, or `NVIDIA_API_KEY` paths. Those code paths were deliberately removed; the router has one provider (`gemini-cli`). Errors should tell the operator to run `manage.py gemini_login`.
- **Rate limits are real.** Google AI Pro tier on `gemini-2.5-pro` is single-digit RPM; flash is the default for a reason. Auto-retry on 429 is in `ChatGeminiCloudCode._post_with_retry` / `_stream`.
- **Tool registration** is import-side-effect — new tools must be wired into `_ensure_builtin_tools_loaded()`.
- **Celery task registration** is import-side-effect — new task modules must be imported from `scheduler/tasks.py`.
- **pgvector image required** — DB must be `pgvector/pgvector:pg16` (the compose default). On a foreign Postgres run `manage.py ensure_pgvector` before `make migrate`.
- **No tests, no CI.** Verification is `manage.py check` + `manage.py codeassist_status` + a smoke chat. Don't claim a change is verified without one of those.
- **Chat turns are synchronous** in `ChatConsumer`. Celery is only for scheduled/background work. Long agent runs that should survive a restart belong on the Kanban queue.
- **Stale Celery messages.** If you see "Received unregistered task" warnings after a major refactor, the Postgres broker queue has stale messages. Purge with `cd surajclaw && ../.venv/bin/celery -A config purge -f`.
- **MCP client is async-on-a-thread.** Don't try to call `tools/mcp/client.py` internals from inside an asyncio context; the dedicated event loop is what makes the sync registry shim work.
</content>
</invoke>