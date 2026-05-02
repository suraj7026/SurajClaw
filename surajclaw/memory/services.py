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
      * Google AI ``embedContent`` endpoint (uses GEMINI_API_KEY).

    Falls back to a zero-vector on failure so retrieval degrades gracefully
    rather than crashing the agent pipeline.
    """
    model = (settings.EMBEDDING_MODEL or "").strip()
    dims = settings.EMBEDDING_DIMENSIONS
    try:
        vec = _embed_gemini(text, model, dims)
    except Exception as exc:  # noqa: BLE001 -- never crash agent turns on embeddings
        logger.warning("embed_text(%s) failed: %s", model, exc)
        return [0.0] * dims

    if len(vec) != dims:
        logger.warning(
            "embed_text: got %d dims, expected %d — padding/truncating",
            len(vec), dims,
        )
        vec = (vec + [0.0] * dims)[:dims]
    return vec


def _is_zero_vector(vec: Sequence[float]) -> bool:
    return not vec or all(abs(value) < 1e-12 for value in vec)


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
    if _is_zero_vector(vec):
        return []
    return list(
        NoteIndex.objects.annotate(distance=CosineDistance("embedding", vec))
        .order_by("distance")[:limit]
    )


def semantic_search_sessions(query: str, limit: int = 5) -> Sequence[SessionEmbedding]:
    vec = embed_text(query)
    if _is_zero_vector(vec):
        return []
    return list(
        SessionEmbedding.objects.annotate(distance=CosineDistance("embedding", vec))
        .order_by("distance")[:limit]
    )


def semantic_search_entities(query: str, limit: int = 5) -> Sequence[Entity]:
    vec = embed_text(query)
    if _is_zero_vector(vec):
        return []
    return list(
        Entity.objects.exclude(embedding=None)
        .annotate(distance=CosineDistance("embedding", vec))
        .order_by("distance")[:limit]
    )


def context_loader(query: str, limit_per_source: int = 3) -> dict[str, list]:
    """Assemble context for the agent before an LLM call.

    Returns a dict with keys `notes`, `sessions`, `entities`, each a list of
    the top-K most relevant rows for `query`. The invocation path injects this
    context before every agent LLM call.
    """
    return {
        "notes": list(semantic_search_notes(query, limit_per_source)),
        "sessions": list(semantic_search_sessions(query, limit_per_source)),
        "entities": list(semantic_search_entities(query, limit_per_source)),
    }


def format_context(context: dict[str, list]) -> str:
    """Render retrieved memory rows for an LLM system prompt."""
    lines: list[str] = []
    for note in context.get("notes", []):
        lines.append(f"Note: {note.title} ({note.filename})\n{note.content_preview}")
    for session in context.get("sessions", []):
        lines.append(f"Session summary: {session.summary_text}")
    for entity in context.get("entities", []):
        lines.append(f"Entity: {entity.entity_type}:{entity.name} {entity.attributes}")
    return "\n\n".join(lines)
