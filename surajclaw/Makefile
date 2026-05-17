# SurajClaw Makefile
#
# Run from this directory (surajclaw/). The venv is expected at
# ../.venv (sibling of surajclaw/). Override with `VENV=path make ...`.

VENV ?= ../.venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
CELERY := $(VENV)/bin/celery
DAPHNE := $(VENV)/bin/daphne

DJANGO_SETTINGS ?= config.settings.development
export DJANGO_SETTINGS_MODULE := $(DJANGO_SETTINGS)

.PHONY: help venv install migrate makemigrations createsuperuser shell \
        dev worker beat celery test lint format collectstatic \
        cli docker-up docker-down docker-logs backup

help:
	@echo "SurajClaw targets:"
	@echo "  make venv            -- create ../.venv"
	@echo "  make install         -- pip install requirements into ../.venv"
	@echo "  make migrate         -- apply DB migrations"
	@echo "  make makemigrations  -- generate new migrations"
	@echo "  make dev             -- run Daphne ASGI server (dev settings)"
	@echo "  make worker          -- run Celery worker"
	@echo "  make beat            -- run Celery Beat scheduler"
	@echo "  make celery          -- run worker + beat concurrently (foreground)"
	@echo "  make shell           -- Django shell"
	@echo "  make test            -- run pytest / django test suite"
	@echo "  make lint            -- ruff check"
	@echo "  make format          -- ruff format"
	@echo "  make cli             -- pip install -e . (registers \`surajclaw\` console script)"
	@echo "  make docker-up       -- docker compose up -d"
	@echo "  make docker-down     -- docker compose down"
	@echo "  make backup          -- pg_dump DB into ../backups/"

venv:
	python3 -m venv $(VENV)

install: venv
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt

migrate:
	$(PY) manage.py migrate

makemigrations:
	$(PY) manage.py makemigrations

createsuperuser:
	$(PY) manage.py createsuperuser

shell:
	$(PY) manage.py shell

dev:
	$(DAPHNE) -b 0.0.0.0 -p 8000 config.asgi:application

worker:
	$(CELERY) -A config worker -l info --concurrency=2

beat:
	$(CELERY) -A config beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler

# Run worker + beat in the foreground for local dev (Ctrl-C stops both).
celery:
	$(CELERY) -A config worker -B -l info --concurrency=2 \
	  --scheduler django_celery_beat.schedulers:DatabaseScheduler

collectstatic:
	$(PY) manage.py collectstatic --noinput

test:
	$(PY) manage.py test

lint:
	$(VENV)/bin/ruff check .

format:
	$(VENV)/bin/ruff format .

# Install the CLI so the `surajclaw` console script lands on PATH (inside
# the same ../.venv used by the Django backend). Run after `make install`.
cli:
	$(PIP) install -e .

docker-up:
	docker compose up -d

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f --tail=100

backup:
	@mkdir -p ../backups
	pg_dump -h $${POSTGRES_HOST:-127.0.0.1} -U $${POSTGRES_USER:-surajclaw} \
	  $${POSTGRES_DB:-surajclaw} > ../backups/surajclaw-$$(date +%Y%m%d-%H%M%S).sql
	@echo "wrote ../backups/surajclaw-$$(date +%Y%m%d-%H%M%S).sql"
