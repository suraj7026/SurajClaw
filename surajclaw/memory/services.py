"""Memory services: embedding + semantic search helpers.

These wrappers keep pgvector queries in one place so the rest of the app
can call `semantic_search(...)` without knowing which model we're using
for embeddings or how the HNSW index is tuned.
"""
from __future__ import annotations

import logging
from typing import Sequence

from django.conf import settings
from pgvector.django import CosineDistance

from memory.models import Entity, NoteIndex, SessionEmbedding

logger = logging.getLogger(__name__)


def embed_text(text: str) -> list[float]:
    """Generate an embedding for ``text``.

    Provider routing:
      * Model name starts with ``gemini-`` or ``models/`` -> Google AI
        ``embedContent`` endpoint (uses GEMINI_API_KEY).
      * Anything else -> Ollama at OLLAMA_BASE_URL (e.g. ``nomic-embed-text``).

    Falls back to a zero-vector on failure so retrieval degrades gracefully
    rather than crashing the agent pipeline.
    """
    model = (settings.EMBEDDING_MODEL or "").strip()
    dims = settings.EMBEDDING_DIMENSIONS
    try:
        if model.startswith("gemini-") or model.startswith("models/"):
            vec = _embed_gemini(text, model, dims)
        else:
            vec = _embed_ollama(text, model)
    except Exception as exc:  # noqa: BLE001 -- never crash the planner on embeddings
        logger.warning("embed_text(%s) failed: %s", model, exc)
        return [0.0] * dims

    if len(vec) != dims:
        logger.warning(
            "embed_text: got %d dims, expected %d — padding/truncating",
            len(vec), dims,
        )
        vec = (vec + [0.0] * dims)[:dims]
    return vec


def _embed_ollama(text: str, model: str) -> list[float]:
    import httpx

    url = f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/embeddings"
    resp = httpx.post(url, json={"model": model, "prompt": text}, timeout=30.0)
    resp.raise_for_status()
    return resp.json().get("embedding") or []


def _embed_gemini(text: str, model: str, dims: int) -> list[float]:
    """Hit the Google AI generative embeddings endpoint via REST.

    We talk REST (not the langchain wrapper) so we can pass
    ``outputDimensionality`` and avoid loading the LC client just for one
    call. Endpoint:
      POST https://generativelanguage.googleapis.com/v1beta/{model}:embedContent
    """
    import httpx

    api_key = getattr(settings, "GEMINI_API_KEY", "") or ""
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY missing; cannot use Gemini embeddings")

    # Google accepts both "gemini-embedding-X" and "models/gemini-embedding-X".
    qualified = model if model.startswith("models/") else f"models/{model}"
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/{qualified}:embedContent"
        f"?key={api_key}"
    )
    body = {
        "model": qualified,
        "content": {"parts": [{"text": text}]},
        # Request a fixed-size embedding so it lines up with EMBEDDING_DIMENSIONS
        # (and our pgvector column width).
        "outputDimensionality": dims,
    }
    resp = httpx.post(url, json=body, timeout=30.0)
    resp.raise_for_status()
    payload = resp.json()
    return (payload.get("embedding") or {}).get("values") or []


def semantic_search_notes(query: str, limit: int = 5) -> Sequence[NoteIndex]:
    """Return the `limit` notes closest to `query` by cosine distance."""
    vec = embed_text(query)
    return list(
        NoteIndex.objects.annotate(distance=CosineDistance("embedding", vec))
        .order_by("distance")[:limit]
    )


def semantic_search_sessions(query: str, limit: int = 5) -> Sequence[SessionEmbedding]:
    vec = embed_text(query)
    return list(
        SessionEmbedding.objects.annotate(distance=CosineDistance("embedding", vec))
        .order_by("distance")[:limit]
    )


def semantic_search_entities(query: str, limit: int = 5) -> Sequence[Entity]:
    vec = embed_text(query)
    return list(
        Entity.objects.exclude(embedding=None)
        .annotate(distance=CosineDistance("embedding", vec))
        .order_by("distance")[:limit]
    )


def context_loader(query: str, limit_per_source: int = 3) -> dict[str, list]:
    """Assemble context for the agent before an LLM call.

    Returns a dict with keys `notes`, `sessions`, `entities`, each a list of
    the top-K most relevant rows for `query`. The agent's planner / executor
    nodes call this before every LLM turn.
    """
    return {
        "notes": list(semantic_search_notes(query, limit_per_source)),
        "sessions": list(semantic_search_sessions(query, limit_per_source)),
        "entities": list(semantic_search_entities(query, limit_per_source)),
    }
