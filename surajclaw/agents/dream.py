"""Dream consolidation worker.

Offline memory-maintenance task triggered by the Celery beat schedule. Not
part of the chat agent loop and not a LangGraph node — it just consolidates
``Entity`` rows, prunes stale memory, and (in future) re-embeds updated notes.

Constraints enforced by construction: this module only touches memory
services and Django ORM. It must never reach into the live tool registry,
agents, or external APIs.
"""
from __future__ import annotations

import logging
import time
from datetime import timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)


def consolidate(*, trigger: str = "auto", sessions_processed: int = 0) -> dict:
    """Run a single Dream cycle, return a summary dict for persistence."""
    from core.models import DreamLog

    t0 = time.monotonic()

    entities_merged = _merge_duplicate_entities()
    entities_pruned = _prune_stale_entities(days=180)
    # ``notes_updated`` is a real ``DreamLog`` column and a public field on
    # the API serializer, but the actual re-indexing pass isn't wired up
    # yet. Until it is, write 0 so the schema stays satisfied without a
    # no-op helper function to maintain.
    notes_updated = 0

    duration = time.monotonic() - t0
    summary_text = (
        f"dream cycle: merged={entities_merged}, pruned={entities_pruned}, "
        f"notes_reindexed={notes_updated}, took {duration:.1f}s"
    )

    DreamLog.objects.create(
        trigger=trigger,
        sessions_processed=sessions_processed,
        entities_merged=entities_merged,
        entities_pruned=entities_pruned,
        notes_updated=notes_updated,
        duration_seconds=duration,
        summary=summary_text,
    )
    logger.info("dream: %s", summary_text)
    return {
        "entities_merged": entities_merged,
        "entities_pruned": entities_pruned,
        "notes_updated": notes_updated,
        "duration_seconds": duration,
    }


def _merge_duplicate_entities() -> int:
    """Placeholder: in the full impl we'd cluster by embedding similarity.

    For now, merge entities that share a normalized `name` within the same
    `entity_type`. Returns the number of merges performed.
    """
    from django.db.models import Count

    from memory.models import Entity

    merges = 0
    dupes = (
        Entity.objects.values("entity_type", "name")
        .annotate(c=Count("id"))
        .filter(c__gt=1)
    )
    for row in dupes:
        group = list(
            Entity.objects.filter(
                entity_type=row["entity_type"],
                name=row["name"],
            ).order_by("last_updated")
        )
        keeper = group[-1]
        merged_attrs = dict(keeper.attributes or {})
        for e in group[:-1]:
            merged_attrs.update(e.attributes or {})
            e.delete()
            merges += 1
        keeper.attributes = merged_attrs
        keeper.save(update_fields=["attributes"])
    return merges


def _prune_stale_entities(*, days: int) -> int:
    from memory.models import Entity

    cutoff = timezone.now() - timedelta(days=days)
    pruned, _ = Entity.objects.filter(last_updated__lt=cutoff).delete()
    return int(pruned)


