"""Model router -- OAuth-Gemini-only.

SurajClaw runs every agent turn against Google Gemini via the Code Assist
endpoint (``cloudcode-pa.googleapis.com``) using OAuth credentials acquired
through ``python manage.py gemini_login``. No static API keys, no other
providers.

The router still resolves a ``ModelChoice`` per turn so that:

* directive overrides (``!model gemini-2.5-flash``) keep working
* the session ``/model`` pin still applies
* you can swap to a different Gemini model id without code edits

But every choice ultimately routes to one provider: ``gemini-cli``.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

from django.conf import settings

logger = logging.getLogger(__name__)


# Kept for backwards compatibility with callers passing task_kind; we no
# longer fan out across providers, so the value just gets logged.
TaskKind = Literal["chat", "code", "tool_loop", "cheap"]


@dataclass
class ModelChoice:
    provider: str
    model: str
    reason: str


def _default_model() -> str:
    return getattr(settings, "GEMINI_OAUTH_MODEL", "gemini-2.5-pro")


def route(
    prompt: str,
    *,
    requires_tools: bool = True,
    complexity_hint: str = "",
    session_id: str | None = None,
    explicit: str | None = None,
    directive_model: str | None = None,
    task_kind: TaskKind = "chat",
) -> ModelChoice:
    """Pick a Gemini model for one agent turn (provider is always ``gemini-cli``)."""
    requested = (explicit or directive_model or "").strip().lower()
    source = "explicit" if explicit else "directive" if directive_model else ""
    if not requested and session_id:
        requested = _read_session_pin(session_id)
        source = "session pin" if requested else ""

    if requested and requested not in {"auto", "gemini", "gemini-cli", "gemini-oauth", "google", "google-oauth"}:
        # A specific model id (e.g. "gemini-2.5-flash") -- honor it verbatim.
        return ModelChoice(
            provider="gemini-cli",
            model=requested,
            reason=f"{source or 'requested'} selected gemini-cli:{requested}",
        )

    return ModelChoice(
        provider="gemini-cli",
        model=_default_model(),
        reason=f"default -> gemini-cli ({_default_model()})",
    )


def _read_session_pin(session_id: str) -> str:
    try:
        from core.models import SystemState
    except Exception as exc:  # noqa: BLE001 -- Django apps may not be ready in tests
        logger.debug("model pin import failed: %s", exc)
        return ""
    try:
        row = SystemState.objects.filter(key=f"model_pin:{session_id}").first()
    except Exception as exc:  # noqa: BLE001 -- DB might not be migrated yet
        logger.debug("model pin lookup failed: %s", exc)
        return ""
    return (row.value or "").lower() if row else ""


def build_llm(choice: ModelChoice):
    """Instantiate the Code Assist chat model for ``choice.model``."""
    if choice.provider != "gemini-cli":
        raise ValueError(
            f"only the OAuth-backed `gemini-cli` provider is supported "
            f"(got {choice.provider!r}). Run `python manage.py gemini_login` "
            f"if you haven't authenticated yet."
        )
    from agents.gemini_cloudcode_chat import ChatGeminiCloudCode

    return ChatGeminiCloudCode(model_name=choice.model)
