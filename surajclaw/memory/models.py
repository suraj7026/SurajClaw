"""Memory models with pgvector embeddings.

Three model kinds live here:

- Entity: structured facts about people / projects / companies
- NoteIndex: pointer + embedding for markdown notes on disk
- SessionEmbedding: embed session summaries for semantic recall

All embedding columns are `pgvector.VectorField`s with an IVFFlat index in
the migration so cosine-distance lookups stay fast as the store grows.
"""
from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from pgvector.django import HnswIndex, VectorField


def _embedding_dims() -> int:
    return settings.EMBEDDING_DIMENSIONS


class Entity(models.Model):
    """Structured facts about a named entity the agent has learned about."""

    class Type(models.TextChoices):
        PERSON = "person", "Person"
        PROJECT = "project", "Project"
        COMPANY = "company", "Company"
        PREFERENCE = "preference", "Preference"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    entity_type = models.CharField(max_length=32, choices=Type.choices)
    name = models.CharField(max_length=255)
    attributes = models.JSONField(default=dict, blank=True)
    source_session = models.ForeignKey(
        "core.Session",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="entities",
    )
    last_updated = models.DateTimeField(auto_now=True)
    embedding = VectorField(dimensions=_embedding_dims(), null=True, blank=True)

    class Meta:
        db_table = "memory_entity"
        ordering = ["-last_updated"]
        constraints = [
            models.UniqueConstraint(
                fields=["entity_type", "name"],
                name="uniq_entity_type_name",
            ),
        ]
        indexes = [
            models.Index(fields=["entity_type"]),
            models.Index(fields=["name"]),
            HnswIndex(
                name="entity_embedding_hnsw",
                fields=["embedding"],
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            ),
        ]

    def __str__(self) -> str:
        return f"{self.entity_type}:{self.name}"


class NoteIndex(models.Model):
    """Pointer to a markdown note on disk plus its embedding.

    The raw markdown lives under `NOTES_DIR`; this row stores metadata so
    we can do semantic search via pgvector without scanning the filesystem.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    filename = models.CharField(max_length=255, unique=True)
    content_preview = models.TextField(blank=True, default="")
    embedding = VectorField(dimensions=_embedding_dims())
    source_session = models.ForeignKey(
        "core.Session",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notes",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "memory_note_index"
        ordering = ["-updated_at"]
        indexes = [
            HnswIndex(
                name="note_embedding_hnsw",
                fields=["embedding"],
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            ),
        ]

    def __str__(self) -> str:
        return self.title


class SessionEmbedding(models.Model):
    """Embedding of a session's summary for "what did we discuss" recall."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.OneToOneField(
        "core.Session",
        on_delete=models.CASCADE,
        related_name="embedding",
    )
    summary_text = models.TextField()
    embedding = VectorField(dimensions=_embedding_dims())
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "memory_session_embedding"
        ordering = ["-created_at"]
        indexes = [
            HnswIndex(
                name="sess_embedding_hnsw",
                fields=["embedding"],
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            ),
        ]

    def __str__(self) -> str:
        return f"SessionEmbedding({self.session_id})"
