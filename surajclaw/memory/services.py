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
    """Generate an embedding via Ollama (nomic-embed-text by default).

    Falls back to a zero-vector on failure so callers can proceed with
    degraded retrieval rather than crashing the agent pipeline.
    """
    import httpx

    payload = {"model": settings.EMBEDDING_MODEL, "prompt": text}
    url = f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/embeddings"
    try:
        resp = httpx.post(url, json=payload, timeout=30.0)
        resp.raise_for_status()
        vec = resp.json().get("embedding") or []
        if len(vec) != settings.EMBEDDING_DIMENSIONS:
            logger.warning(
                "embed_text: got %d dims, expected %d — padding/truncating",
                len(vec), settings.EMBEDDING_DIMENSIONS,
            )
            vec = (vec + [0.0] * settings.EMBEDDING_DIMENSIONS)[
                : settings.EMBEDDING_DIMENSIONS
            ]
        return vec
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("embed_text failed: %s", exc)
        return [0.0] * settings.EMBEDDING_DIMENSIONS


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
