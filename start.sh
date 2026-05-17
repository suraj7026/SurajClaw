#!/usr/bin/env bash
# SurajClaw all-in-one dev launcher.
#
#   ./start.sh           -- web + worker + beat, foreground with combined logs
#   ./start.sh web       -- web only (skips celery)
#   ./start.sh --install -- pip install requirements before booting
#
# Ctrl-C cleanly shuts every background process down.

set -euo pipefail

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$ROOT/surajclaw"
VENV="$ROOT/.venv"
LOG_DIR="$ROOT/.run/logs"
PID_DIR="$ROOT/.run/pids"

PY="$VENV/bin/python"
PIP="$VENV/bin/pip"
DAPHNE="$VENV/bin/daphne"
CELERY="$VENV/bin/celery"

mkdir -p "$LOG_DIR" "$PID_DIR"

# ---------------------------------------------------------------------------
# Colors (NO_COLOR or non-TTY disables)
# ---------------------------------------------------------------------------
if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
    BLUE=$'\033[34m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; RED=$'\033[31m'; DIM=$'\033[2m'; RESET=$'\033[0m'
else
    BLUE=""; GREEN=""; YELLOW=""; RED=""; DIM=""; RESET=""
fi

log()  { printf "%s[surajclaw]%s %s\n" "$BLUE"  "$RESET" "$*"; }
ok()   { printf "%s[surajclaw]%s %s\n" "$GREEN" "$RESET" "$*"; }
warn() { printf "%s[surajclaw]%s %s\n" "$YELLOW" "$RESET" "$*" >&2; }
die()  { printf "%s[surajclaw]%s %s\n" "$RED"   "$RESET" "$*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Args
# ---------------------------------------------------------------------------
INSTALL=0
SERVICES=("web" "worker" "beat")

for arg in "$@"; do
    case "$arg" in
        --install) INSTALL=1 ;;
        web|worker|beat)
            # First positional sets the service list to just that one.
            if [[ "${USER_PICKED_SERVICES:-0}" != "1" ]]; then
                SERVICES=()
                USER_PICKED_SERVICES=1
            fi
            SERVICES+=("$arg")
            ;;
        -h|--help)
            sed -n '2,9p' "$0"; exit 0 ;;
        *) die "unknown arg: $arg" ;;
    esac
done

# ---------------------------------------------------------------------------
# Preflight: virtualenv
# ---------------------------------------------------------------------------
if [[ ! -x "$PY" ]]; then
    die "virtualenv not found at $VENV. Run: (cd $APP_DIR && make install)"
fi

if [[ "$INSTALL" == "1" ]]; then
    log "installing/upgrading Python dependencies"
    "$PIP" install --upgrade pip >/dev/null
    "$PIP" install -r "$APP_DIR/requirements.txt"
fi

# ---------------------------------------------------------------------------
# Preflight: Docker (only when we'll need it)
# ---------------------------------------------------------------------------
if [[ " ${SERVICES[*]} " == *" web "* || " ${SERVICES[*]} " == *" worker "* || " ${SERVICES[*]} " == *" beat "* ]]; then
    if ! command -v docker >/dev/null 2>&1; then
        die "docker CLI not found. Install Docker Desktop or set up postgres yourself."
    fi
    if ! docker info >/dev/null 2>&1; then
        die "Docker is not running. Open Docker Desktop and re-run."
    fi
fi

# ---------------------------------------------------------------------------
# Postgres via compose (idempotent)
# ---------------------------------------------------------------------------
log "ensuring postgres is up"
(cd "$APP_DIR" && docker compose up -d db) >/dev/null
log "waiting for postgres to be healthy"
for i in {1..30}; do
    if (cd "$APP_DIR" && docker compose exec -T db pg_isready -U "${POSTGRES_USER:-surajclaw}") >/dev/null 2>&1; then
        ok "postgres ready"
        break
    fi
    sleep 1
    if [[ $i -eq 30 ]]; then die "postgres never became healthy"; fi
done

# ---------------------------------------------------------------------------
# Migrations
# ---------------------------------------------------------------------------
export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-config.settings.development}"
log "running migrations"
(cd "$APP_DIR" && "$PY" manage.py migrate --noinput)

# ---------------------------------------------------------------------------
# Process management
# ---------------------------------------------------------------------------
declare -a PIDS=()
declare -a NAMES=()
declare -a LOGS=()

start_proc() {
    local name="$1"; shift
    local logfile="$LOG_DIR/$name.log"
    : > "$logfile"
    (cd "$APP_DIR" && "$@") >>"$logfile" 2>&1 &
    local pid=$!
    echo "$pid" > "$PID_DIR/$name.pid"
    PIDS+=("$pid")
    NAMES+=("$name")
    LOGS+=("$logfile")
    ok "started $name (pid $pid, log $logfile)"
}

cleanup() {
    echo ""
    log "shutting down..."
    for i in "${!PIDS[@]}"; do
        local pid="${PIDS[$i]}"
        local name="${NAMES[$i]}"
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
            log "stopped $name (pid $pid)"
        fi
        rm -f "$PID_DIR/$name.pid"
    done
    # Give them a moment to exit gracefully, then SIGKILL stragglers.
    sleep 1
    for pid in "${PIDS[@]}"; do
        kill -9 "$pid" 2>/dev/null || true
    done
    ok "all stopped"
    exit 0
}
trap cleanup INT TERM

# ---------------------------------------------------------------------------
# Launch services
# ---------------------------------------------------------------------------
for svc in "${SERVICES[@]}"; do
    case "$svc" in
        web)
            start_proc web "$DAPHNE" -b 0.0.0.0 -p 8000 config.asgi:application
            ;;
        worker)
            start_proc worker "$CELERY" -A config worker -l info --concurrency=2
            ;;
        beat)
            start_proc beat "$CELERY" -A config beat -l info \
                --scheduler django_celery_beat.schedulers:DatabaseScheduler
            ;;
    esac
done

echo ""
ok "SurajClaw is up"
log "CLI:      surajclaw login   # then  surajclaw chat / surajclaw tui"
log "API:      http://127.0.0.1:8000/"
log "WebUI:    http://127.0.0.1:8000/ui/"
log "Logs:     tail -f $LOG_DIR/*.log"
echo ""
log "${DIM}streaming combined logs below (Ctrl-C to stop everything)${RESET}"
echo ""

# Stream all logs prefixed by service name. ``tail -f`` exits when its
# parent shell does, and we trap signals to clean up child PIDs above.
tail -F -n 0 "${LOGS[@]}" 2>/dev/null | awk -v dim="$DIM" -v reset="$RESET" '
    /^==>/ { svc=$2; sub(/.*\//, "", svc); sub(/\.log <==$/, "", svc); next }
    { printf "%s[%s]%s %s\n", dim, svc, reset, $0 }
' &
TAIL_PID=$!
PIDS+=("$TAIL_PID")
NAMES+=("tail")

# Wait on any subprocess; cleanup() fires on signal.
wait
