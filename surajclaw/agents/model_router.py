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


def route(prompt: str, *, requires_tools: bool, complexity_hint: str = "") -> ModelChoice:
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
