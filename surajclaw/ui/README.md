# SurajClaw Operator Console

React 18 + Vite + TailwindCSS dashboard for the SurajClaw personal AI assistant. Implements the four-page operator UI (Dashboard, Pipeline, Memory, Tasks) and an Integrations panel for managing connected Google accounts.

## Dev

```bash
cd surajclaw/ui
npm install
npm run dev          # http://localhost:5173
```

The dev server proxies `/api/*` and `/ws/*` to `http://localhost:8000` (the Django backend). Start the backend separately:

```bash
cd surajclaw
docker compose up         # or: python manage.py runserver
```

## Auth

Login via `POST /api/auth/login/` with username/password — returns a DRF auth token that the app stores in `localStorage` and sends on every request as `Authorization: Token <key>`.

Create the operator user via Django:

```bash
python manage.py createsuperuser
```

## Build

```bash
npm run build        # outputs to dist/
```

The built `dist/` folder can be served by Nginx in front of Daphne, or mounted into the `web` Docker service as static files.

## Folder layout

```
src/
  api/           fetch client + typed endpoint helpers
  hooks/         useAuth, useWebSocket, useApi
  context/       AuthContext, WebSocketContext
  components/
    layout/      Shell, TopAppBar, SideNav, MobileNav
    shared/      StatusIndicator, ProgressBar, MetricCard, LogEntry
    chat/        ChatPanel, MessageBubble
  pages/         Dashboard, Pipeline, Memory, Tasks, Integrations, Login
```
