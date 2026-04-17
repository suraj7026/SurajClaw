"""Model routing: choose Gemma (local) vs Gemini (cloud).

Routing heuristics:
- Default to Gemma 4 for anything classified as simple (short prompts,
  single-tool plans, retrieval summaries).
- Escalate to Gemini when (a) the planner flags the request as complex,
  (b) an output token budget exceeds the Gemma context, or (c) the user
  opts in with the `--gemini` hint.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from django.conf import settings

logger = logging.getLogger(__name__)


@dataclass
class ModelChoice:
    provider: str  # "ollama" | "gemini"
    model: str
    reason: str


SIMPLE_TOKEN_BUDGET = 4_000  # Gemma comfort zone on 4GB GPU


def route(
    prompt: str,
    *,
    requires_tools: bool,
    complexity_hint: str = "",
    session_id: str | None = None,
    directive_model: str | None = None,
) -> ModelChoice:
    """Pick a model for this turn.

    Priority order (highest first):

    1. ``directive_model`` — user typed ``!model gemini`` for this turn.
    2. Per-session pin set via ``/model`` slash command (SystemState row
       ``model_pin:<session_id>``).
    3. Legacy ``--gemini`` substring + planner-supplied complexity hint.
    4. Token-budget heuristic.
    5. Default to local Gemma.
    """
    explicit = (directive_model or "").lower()
    if not explicit and session_id:
        explicit = _read_session_pin(session_id)

    if explicit == "gemini":
        return ModelChoice(
            provider="gemini",
            model=settings.GEMINI_MODEL,
            reason="explicit user directive: gemini",
        )
    if explicit in ("gemma", "ollama"):
        return ModelChoice(
            provider="ollama",
            model=settings.OLLAMA_MODEL,
            reason="explicit user directive: gemma",
        )

    if "--gemini" in prompt.lower() or complexity_hint == "high":
        return ModelChoice(
            provider="gemini",
            model=settings.GEMINI_MODEL,
            reason="explicit gemini request or high-complexity hint",
        )

    approx_tokens = len(prompt) // 4  # rough
    if approx_tokens > SIMPLE_TOKEN_BUDGET:
        return ModelChoice(
            provider="gemini",
            model=settings.GEMINI_MODEL,
            reason=f"prompt ~{approx_tokens} tokens > gemma budget",
        )

    if requires_tools and complexity_hint == "multi-tool":
        return ModelChoice(
            provider="gemini",
            model=settings.GEMINI_MODEL,
            reason="multi-tool plan benefits from stronger model",
        )

    return ModelChoice(
        provider="ollama",
        model=settings.OLLAMA_MODEL,
        reason="default: local gemma is sufficient",
    )


def _read_session_pin(session_id: str) -> str:
    """Read SystemState row written by ``/model`` slash command.

    Lazy import: ``model_router`` is hot path; we don't want Django ORM
    pulled in at module import for tests that only call ``route``.
    """
    try:
        from core.models import SystemState
    except ImportError:
        return ""
    try:
        row = SystemState.objects.filter(key=f"model_pin:{session_id}").first()
    except Exception as exc:  # noqa: BLE001 -- DB might not be migrated yet
        logger.debug("model pin lookup failed: %s", exc)
        return ""
    return (row.value or "").lower() if row else ""


def build_llm(choice: ModelChoice):
    """Instantiate a LangChain chat model for the chosen provider.

    Deferred imports keep startup fast and let a Gemma-only deployment work
    without Gemini credentials present.
    """
    if choice.provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=choice.model,
            api_key=settings.GEMINI_API_KEY,
            temperature=0.2,
        )

    from langchain_ollama import ChatOllama

    return ChatOllama(
        model=choice.model,
        base_url=settings.OLLAMA_BASE_URL,
        temperature=0.2,
    )
