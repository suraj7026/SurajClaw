"""Google Tasks tools."""
from __future__ import annotations

from typing import Any

from agents.types import ToolDefinition
from core.google_accounts import GoogleAccount
from tools.google._common import per_account_fanout, single_account, tasks_client
from tools.registry import register_tool


def list_tasklists(account_label: str = "all") -> dict[str, Any]:
    def _one(account: GoogleAccount) -> dict[str, Any]:
        service = tasks_client(account)
        result = service.tasklists().list(maxResults=100).execute()
        items = [
            {"tasklist_id": tl.get("id"), "title": tl.get("title", "")}
            for tl in result.get("items", []) or []
        ]
        return {"items": items, "output": f"{len(items)} tasklist(s)"}

    return per_account_fanout(account_label, _one)


def list_tasks(
    account_label: str = "all",
    tasklist_id: str = "@default",
    show_completed: bool = False,
    limit: int = 50,
) -> dict[str, Any]:
    def _one(account: GoogleAccount) -> dict[str, Any]:
        service = tasks_client(account)
        result = (
            service.tasks()
            .list(
                tasklist=tasklist_id,
                showCompleted=show_completed,
                maxResults=max(1, min(limit, 100)),
            )
            .execute()
        )
        items = []
        for t in result.get("items", []) or []:
            items.append(
                {
                    "task_id": t.get("id"),
                    "title": t.get("title", ""),
                    "notes": t.get("notes", ""),
                    "due": t.get("due"),
                    "status": t.get("status"),
                    "tasklist_id": tasklist_id,
                }
            )
        return {"items": items, "output": f"{len(items)} task(s) on {tasklist_id}"}

    return per_account_fanout(account_label, _one)


def create_task(
    account_label: str,
    title: str,
    tasklist_id: str = "@default",
    notes: str = "",
    due: str = "",
) -> dict[str, Any]:
    if not title:
        return {"ok": False, "output": "title is required", "error": "missing_title"}
    body: dict[str, Any] = {"title": title}
    if notes:
        body["notes"] = notes
    if due:
        body["due"] = due

    def _one(account: GoogleAccount) -> dict[str, Any]:
        service = tasks_client(account)
        task = service.tasks().insert(tasklist=tasklist_id, body=body).execute()
        return {
            "output": f"created task '{title}' on {tasklist_id}",
            "structured": {"task_id": task.get("id"), "tasklist_id": tasklist_id},
        }

    return single_account(account_label, _one)


def update_task(
    account_label: str,
    task_id: str,
    tasklist_id: str = "@default",
    title: str = "",
    notes: str = "",
    due: str = "",
    completed: bool | None = None,
) -> dict[str, Any]:
    if not task_id:
        return {"ok": False, "output": "task_id is required", "error": "missing_task_id"}
    patch: dict[str, Any] = {}
    if title:
        patch["title"] = title
    if notes:
        patch["notes"] = notes
    if due:
        patch["due"] = due
    if completed is True:
        patch["status"] = "completed"
    elif completed is False:
        patch["status"] = "needsAction"
        patch["completed"] = None
    if not patch:
        return {"ok": False, "output": "no fields to update", "error": "empty_patch"}

    def _one(account: GoogleAccount) -> dict[str, Any]:
        service = tasks_client(account)
        task = service.tasks().patch(tasklist=tasklist_id, task=task_id, body=patch).execute()
        return {
            "output": f"updated task {task_id}",
            "structured": {"task_id": task.get("id"), "status": task.get("status")},
        }

    return single_account(account_label, _one)


def delete_task(
    account_label: str,
    task_id: str,
    tasklist_id: str = "@default",
) -> dict[str, Any]:
    if not task_id:
        return {"ok": False, "output": "task_id is required", "error": "missing_task_id"}

    def _one(account: GoogleAccount) -> dict[str, Any]:
        service = tasks_client(account)
        service.tasks().delete(tasklist=tasklist_id, task=task_id).execute()
        return {"output": f"deleted task {task_id}", "structured": {"task_id": task_id}}

    return single_account(account_label, _one)


def register() -> None:
    register_tool(ToolDefinition(
        id="google.tasks.list_tasklists",
        callable=list_tasklists,
        description="List Google Tasks tasklists. Args: account_label.",
    ))
    register_tool(ToolDefinition(
        id="google.tasks.list_tasks",
        callable=list_tasks,
        description=(
            "List tasks in a tasklist. Args: account_label, tasklist_id "
            "(default '@default'), show_completed, limit."
        ),
    ))
    register_tool(ToolDefinition(
        id="google.tasks.create_task",
        callable=create_task,
        description=(
            "Create a task. Args: account_label (single), title, tasklist_id, "
            "notes, due (RFC3339)."
        ),
        approval_required=True,
    ))
    register_tool(ToolDefinition(
        id="google.tasks.update_task",
        callable=update_task,
        description=(
            "Patch a task. Args: account_label, task_id, tasklist_id, optional "
            "title, notes, due, completed (bool)."
        ),
        approval_required=True,
    ))
    register_tool(ToolDefinition(
        id="google.tasks.delete_task",
        callable=delete_task,
        description="Delete a task. Args: account_label, task_id, tasklist_id.",
        approval_required=True,
    ))
