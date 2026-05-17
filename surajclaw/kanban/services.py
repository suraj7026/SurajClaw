"""Service helpers for creating + querying KanbanTasks."""
from __future__ import annotations

from typing import Any


def enqueue(
    title: str,
    prompt: str,
    *,
    agent_id: str = "",
    model_provider: str = "",
    priority: int = 0,
    context: dict[str, Any] | None = None,
    max_attempts: int = 3,
    created_by: str = "",
):
    from kanban.models import KanbanTask

    return KanbanTask.objects.create(
        title=title[:200],
        prompt=prompt,
        agent_id=agent_id[:64],
        model_provider=model_provider[:32],
        priority=priority,
        context=context or {},
        max_attempts=max_attempts,
        created_by=created_by[:128],
    )


def list_tasks(status: str = "", limit: int = 50):
    from kanban.models import KanbanTask

    qs = KanbanTask.objects.all()
    if status:
        qs = qs.filter(status=status)
    return list(qs[:limit])


def cancel(task_id):
    from kanban.models import KanbanTask

    updated = KanbanTask.objects.filter(
        id=task_id,
        status__in=[KanbanTask.Status.QUEUED, KanbanTask.Status.CLAIMED],
    ).update(status=KanbanTask.Status.CANCELLED)
    return updated > 0
