# AGENTS.md

## Scope
- Real application code lives in `surajclaw/`; the repo root mainly holds `.env`, docs, and editor/OpenCode metadata.
- `PersonalAI_SoftwareDoc.md` is design intent, not runtime truth. When it conflicts with code or config under `surajclaw/`, trust the code.

## Stack And Entrypoints
- Backend is Django + Channels + Celery + Postgres/pgvector. Redis is not used; Celery uses Postgres for broker/results. There is no browser UI: the operator surface is the `surajclaw` CLI in `surajclaw/clawcli/`.
- The CLI is a WebSocket client. It authenticates via DRF token (`/api/auth/login/`) and talks to the existing `ws/chat/<session_uuid>/` consumer in `surajclaw/chat/consumers.py`. Slash commands (`/help`, `/agents`, `/agent`, `/stop`, `/approve`, ...) and inline directives (`!model`, `!thinking`) are server-rendered, so the CLI just streams frames.
- `surajclaw/manage.py` defaults to `config.settings.development`.
- HTTP and WebSocket traffic both enter through `surajclaw/config/asgi.py`; `make dev` runs Daphne on `:8000`. The HTTP root `/` returns a small JSON info doc — there is no HTML page.
- Chat turns run inline in `chat/consumers.py`; the consumer passes a direct token callback to `agents.graph.run_turn()`. Celery is only needed for scheduled/background jobs.
- `agents/orchestrator.py` is intentionally thin. Normal chat invokes the `general` agent, which uses Gemini tool calling and can delegate to `google_workspace`, `code_executor`, or `notes` subagents.

## Commands
- Run backend commands from `surajclaw/`. The `Makefile` assumes the virtualenv lives at `../.venv`, not inside `surajclaw/`.
- Setup: `cd surajclaw && make install`
- Migrations: `cd surajclaw && make migrate`
- Core service for local dev: `cd surajclaw && docker compose up -d db`
- Backend server: `cd surajclaw && make dev`
- Worker / scheduler: `cd surajclaw && make worker`, `cd surajclaw && make beat`, or `cd surajclaw && make celery`
- CLI install (registers the `surajclaw` console script): `cd surajclaw && make cli`
- CLI usage: `surajclaw login`, then `surajclaw chat` (line-based REPL) or `surajclaw tui` (full-screen Textual UI). Other subcommands: `surajclaw whoami`, `surajclaw doctor`, `surajclaw status`, `surajclaw logout`.
- Full stack via Compose: `cd surajclaw && docker compose up` (just Django + Postgres + Celery; the CLI runs on the host).
- Health check: `cd surajclaw && python manage.py doctor` (or `surajclaw doctor` from any shell with stored credentials)
- Google account bootstrap: `cd surajclaw && python manage.py google_oauth_login --account <label>`

## Data And Env
- The environment file lives at the repo root as `.env`; `config/settings/base.py` loads `../.env`, and `docker-compose.yml` also points at that root file.
- If you point `POSTGRES_HOST` at a fresh non-`pgvector/pgvector` Postgres, run `cd surajclaw && python manage.py ensure_pgvector` before `make migrate`.
- Leave `CELERY_BROKER_URL` blank to derive a Postgres SQLAlchemy broker URL from `POSTGRES_*`; `CELERY_RESULT_BACKEND` should stay `django-db`.
- OAuth refresh tokens are stored per account under the repo-root `google_tokens/` directory.
- Owner auth fails closed. Unauthenticated web/Telegram flows are denied unless the user is logged in through Django auth or `OWNER_ALLOW_FROM` / `TELEGRAM_OWNER_ID` is set. `python manage.py doctor` checks this.

## Verification
- `cd surajclaw && make test` is just `python manage.py test`.
- There are currently no checked-in Django test cases, no `pytest` setup, and no `.github/workflows/` or pre-commit config. Expect manual smoke testing to be the real verification path.
- Prefer targeted checks: `cd surajclaw && python manage.py check`, `cd surajclaw && python manage.py doctor`, and `cd surajclaw && python manage.py test_gmail --account <label>`.
- For the CLI, smoke test with `surajclaw doctor` and a short `surajclaw chat` round-trip (send "hello", expect a `final` frame).
- `make lint` / `make format` call Ruff, but `surajclaw/requirements.txt` does not install Ruff. Do not assume the lint command works in a fresh clone.

## Wiring Gotchas
- Tool registration is import-side-effect based. If you add a new tool module, wire it into `tools.registry._ensure_builtin_tools_loaded()` or it never becomes visible.
- Celery task registration is also import-side-effect based. New task modules must be imported from `scheduler/tasks.py` or workers will reject them as unregistered.
- The CLI in `surajclaw/clawcli/` is a thin WebSocket client; it does NOT re-implement the agent loop. Slash commands and directives live server-side in `chat/commands.py` and `chat/directives.py`. New chat features go there. Two front-ends: line-based REPL (`clawcli/chat.py`) and full-screen TUI (`clawcli/tui.py`, Textual). Both consume the same WS frame stream and share auth via `_resolve_chat_auth` in `main.py`.
- Live LLM streaming: `agents/subgraphs/reactive.py::_stream_llm` drives `bound.stream(...)` and emits `{type: "token", ...}` frames on the consumer's `on_event`. If the bound runnable can't stream, it falls back to `.invoke()` transparently.
- The CLI server URL comes from (in order): `--server` flag, stored credentials, `SURAJCLAW_SERVER` env var, default `http://127.0.0.1:8000`. Token auth via DRF (`Authorization: Token <key>`); WebSocket reuses the same token via the `?token=` query string that `ChatConsumer._identity_from_scope` already reads.
- `pip install -e .` (or `make cli`) registers the `surajclaw` console script via `pyproject.toml`; the package itself is `surajclaw/clawcli/`.
