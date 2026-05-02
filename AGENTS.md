# AGENTS.md

## Scope
- Real application code lives in `surajclaw/`; the repo root mainly holds `.env`, docs, and editor/OpenCode metadata.
- `PersonalAI_SoftwareDoc.md` is design intent, not runtime truth. When it conflicts with code or config under `surajclaw/`, trust the code.

## Stack And Entrypoints
- Backend is Django + Channels + Celery + Postgres/pgvector. Redis is not used; Celery uses Postgres for broker/results. Frontend is React/Vite in `surajclaw/ui/`.
- There are two web surfaces: Django serves the lightweight chat page from `surajclaw/chat/` at `/`, and the operator console lives in `surajclaw/ui/`.
- `surajclaw/manage.py` defaults to `config.settings.development`.
- HTTP and WebSocket traffic both enter through `surajclaw/config/asgi.py`; `make dev` runs Daphne on `:8000`.
- Chat turns run inline in `chat/consumers.py`; the consumer passes a direct token callback to `agents.graph.run_turn()`. Celery is only needed for scheduled/background jobs.
- `agents/orchestrator.py` is intentionally thin. Normal chat invokes the `general` agent, which uses Gemini tool calling and can delegate to `google_workspace`, `code_executor`, or `notes` subagents.

## Commands
- Run backend commands from `surajclaw/`. The `Makefile` assumes the virtualenv lives at `../.venv`, not inside `surajclaw/`.
- Setup: `cd surajclaw && make install`
- Migrations: `cd surajclaw && make migrate`
- Core service for local dev: `cd surajclaw && docker compose up -d db`
- Backend server: `cd surajclaw && make dev`
- Worker / scheduler: `cd surajclaw && make worker`, `cd surajclaw && make beat`, or `cd surajclaw && make celery`
- Frontend: `cd surajclaw/ui && npm install && npm run dev`
- Full stack via Compose: `cd surajclaw && docker compose up`
- Health check: `cd surajclaw && python manage.py doctor`
- Google account bootstrap: `cd surajclaw && python manage.py google_oauth_login --account <label>`

## Data And Env
- The environment file lives at the repo root as `.env`; `config/settings/base.py` loads `../.env`, and `docker-compose.yml` also points at that root file.
- If you point `POSTGRES_HOST` at a fresh non-`pgvector/pgvector` Postgres, run `cd surajclaw && python manage.py ensure_pgvector` before `make migrate`.
- Leave `CELERY_BROKER_URL` blank to derive a Postgres SQLAlchemy broker URL from `POSTGRES_*`; `CELERY_RESULT_BACKEND` should stay `django-db`.
- OAuth refresh tokens are stored per account under the repo-root `google_tokens/` directory.
- Owner auth fails closed. Unauthenticated web/Telegram flows are denied unless the user is logged in through Django auth or `OWNER_ALLOW_FROM` / `TELEGRAM_OWNER_ID` is set. `python manage.py doctor` checks this.

## Verification
- `cd surajclaw && make test` is just `python manage.py test`.
- There are currently no checked-in Django or frontend test cases, no `pytest`/Vitest setup, and no `.github/workflows/` or pre-commit config. Expect manual smoke testing to be the real verification path.
- Prefer targeted checks: `cd surajclaw && python manage.py doctor`, `cd surajclaw && python manage.py test_gmail --account <label>`, and `cd surajclaw/ui && npm run build`.
- `make lint` / `make format` call Ruff, but `surajclaw/requirements.txt` does not install Ruff. `ui/package.json` defines `npm run lint`, but the repo does not currently declare ESLint or a repo-local ESLint config. Do not assume either lint command works in a fresh clone.

## Wiring Gotchas
- Tool registration is import-side-effect based. If you add a new tool module, wire it into `tools.registry._ensure_builtin_tools_loaded()` or it never becomes visible.
- Celery task registration is also import-side-effect based. New task modules must be imported from `scheduler/tasks.py` or workers will reject them as unregistered.
- Vite dev proxy defaults to `http://localhost:8000` and forwards `/api`, `/ws`, `/admin`, and `/static`; keep `VITE_API_BASE_URL` and `VITE_WS_BASE_URL` blank for same-origin dev unless you intentionally need cross-origin URLs.
- `surajclaw/ui/vite.config.ts` is the source file. The repo also tracks emitted `vite.config.js` and `vite.config.d.ts` from `tsc -b`, so edit the `.ts` file first.
