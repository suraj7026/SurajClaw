"""Markdown note tools backed by pgvector indexes."""
from __future__ import annotations

import re
from pathlib import Path

from django.conf import settings

from agents.types import ToolDefinition
from tools.registry import register_tool


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "note"


def _notes_dir() -> Path:
    path = Path(settings.NOTES_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


def notes_write(title: str, content: str, session_id: str | None = None) -> dict:
    from agents.graph import _session_pk
    from core.models import Session
    from memory.models import NoteIndex
    from memory.services import embed_text

    filename = f"{_slug(title)}.md"
    path = _notes_dir() / filename
    path.write_text(content, encoding="utf-8")
    session = None
    if session_id:
        session = Session.objects.filter(id=_session_pk(session_id)).first()
    note, _ = NoteIndex.objects.update_or_create(
        filename=filename,
        defaults={
            "title": title,
            "content_preview": content[:500],
            "embedding": embed_text(f"{title}\n\n{content}"),
            "source_session": session,
        },
    )
    return {
        "ok": True,
        "output": f"Wrote note {note.title} ({filename}).",
        "structured": {"id": str(note.id), "filename": filename, "path": str(path)},
    }


def notes_search(query: str, limit: int = 5) -> dict:
    from memory.services import semantic_search_notes

    notes = semantic_search_notes(query, limit=max(1, min(limit, 20)))
    lines = [f"{note.title} ({note.filename})\n{note.content_preview}" for note in notes]
    return {
        "ok": True,
        "output": "\n\n".join(lines) or "No notes found.",
        "structured": {"notes": [{"id": str(note.id), "title": note.title, "filename": note.filename} for note in notes]},
    }


def notes_list(limit: int = 10) -> dict:
    from memory.models import NoteIndex

    notes = list(NoteIndex.objects.order_by("-updated_at")[: max(1, min(limit, 100))])
    lines = [f"{note.title} ({note.filename})" for note in notes]
    return {
        "ok": True,
        "output": "\n".join(lines) or "No notes indexed yet.",
        "structured": {"notes": [{"id": str(note.id), "title": note.title, "filename": note.filename} for note in notes]},
    }


register_tool(ToolDefinition("notes.write", notes_write, "Write or update a Markdown note and index it."))
register_tool(ToolDefinition("notes.search", notes_search, "Search indexed Markdown notes semantically."))
register_tool(ToolDefinition("notes.list", notes_list, "List recent notes."))
