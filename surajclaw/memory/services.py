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
    """Generate an embedding for ``text`` using the OAuth-backed Code Assist API.

    Uses the same Google Gemini OAuth credentials as the chat agent
    (``manage.py gemini_login``). Falls back to a zero-vector on any
    failure so retrieval degrades gracefully rather than crashing the
    agent pipeline -- callers must guard against the zero case via
    ``_is_zero_vector`` before issuing the pgvector search.
    """
    model = (settings.EMBEDDING_MODEL or "").strip()
    dims = settings.EMBEDDING_DIMENSIONS
    try:
        vec = _embed_via_oauth(text, model, dims)
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


def _embed_via_oauth(text: str, model: str, dims: int) -> list[float]:
    """Embed via the Generative Language API using the gemini_login OAuth token.

    The Code Assist endpoint (``cloudcode-pa.googleapis.com``) only exposes
    ``generateContent`` / ``streamGenerateContent`` — it returns 404 for any
    embed path. Embeddings live on a separate Google service:

        POST https://generativelanguage.googleapis.com/v1beta/models/{model}:embedContent

    The ``cloud-platform`` OAuth scope that ``gemini_login`` already
    requests covers this service, so we reuse the same bearer token.
    """
    import httpx

    from agents.gemini_oauth import (
        CODE_ASSIST_USER_AGENT,
        get_valid_access_token,
        load_credentials,
    )

    creds = load_credentials()
    if creds is None:
        raise RuntimeError(
            "no Gemini OAuth credentials; run `python manage.py gemini_login`"
        )
    access_token = get_valid_access_token()

    # The Generative Language API expects bare model ids ("text-embedding-004"),
    # NOT the qualified "models/text-embedding-004" form Code Assist uses.
    bare_model = model.removeprefix("models/")
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{bare_model}:embedContent"
    )
    body: dict[str, object] = {
        "content": {"parts": [{"text": text}]},
    }
    # ``outputDimensionality`` is only valid for models that support it
    # (text-embedding-004 supports 256-768; gemini-embedding-001 supports
    # arbitrary dims). Always include it; the server ignores it for models
    # that don't.
    body["outputDimensionality"] = dims
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "User-Agent": CODE_ASSIST_USER_AGENT,
    }
    resp = httpx.post(url, json=body, headers=headers, timeout=30.0)
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
