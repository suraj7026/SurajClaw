"""Model selection for the Gemini-only agent runtime."""
from __future__ import annotations

import logging
from dataclasses import dataclass

from django.conf import settings

logger = logging.getLogger(__name__)


@dataclass
class ModelChoice:
    provider: str
    model: str
    reason: str


def route(
    prompt: str,
    *,
    requires_tools: bool,
    complexity_hint: str = "",
    session_id: str | None = None,
    explicit: str | None = None,
    directive_model: str | None = None,
) -> ModelChoice:
    """Choose the Gemini model for a turn.

    ``explicit`` is the strongest override, followed by an inline directive,
    followed by the per-session ``/model`` pin. ``gemini`` is treated as an
    alias for ``settings.GEMINI_MODEL``; any other non-auto value is treated as
    the exact Gemini model name to call.
    """
    requested = (explicit or directive_model or "").strip().lower()
    source = "explicit" if explicit else "directive" if directive_model else "default"
    if not requested and session_id:
        requested = _read_session_pin(session_id)
        source = "session pin" if requested else "default"

    if requested and requested != "auto":
        model = settings.GEMINI_MODEL if requested == "gemini" else requested
        return ModelChoice(
            provider="gemini",
            model=model,
            reason=f"{source} selected {model}",
        )

    return ModelChoice(
        provider="gemini",
        model=settings.GEMINI_MODEL,
        reason=f"default Gemini model {settings.GEMINI_MODEL}",
    )


def _read_session_pin(session_id: str) -> str:
    """Read SystemState row written by ``/model`` slash command.

    Lazy import: ``model_router`` is hot path; we don't want Django ORM
    pulled in at module import for tests that only call ``route``.
    """
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
    """Instantiate the configured Gemini chat model."""
    from langchain_google_genai import ChatGoogleGenerativeAI

    if not settings.GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is not configured")

    return ChatGoogleGenerativeAI(
        model=choice.model,
        api_key=settings.GEMINI_API_KEY,
        temperature=0.2,
        convert_system_message_to_human=True,
    )
