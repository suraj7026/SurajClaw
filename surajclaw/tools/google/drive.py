"""Google Drive tools.

Constrained to drive.file scope (per DEFAULT_SCOPES in api/google.py), which
means the agent only sees files it created or that were explicitly shared
through the API. ``search_files`` therefore returns app-scoped results, not
the user's entire Drive.
"""
from __future__ import annotations

import io
from typing import Any

from agents.types import ToolDefinition
from core.google_accounts import GoogleAccount
from tools.google._common import drive_client, per_account_fanout, single_account
from tools.registry import register_tool


def search_files(
    account_label: str = "all",
    query: str = "",
    limit: int = 20,
) -> dict[str, Any]:
    def _one(account: GoogleAccount) -> dict[str, Any]:
        service = drive_client(account)
        q = query or "trashed = false"
        result = (
            service.files()
            .list(
                q=q,
                pageSize=max(1, min(limit, 100)),
                fields="files(id,name,mimeType,modifiedTime,size,webViewLink)",
            )
            .execute()
        )
        items = []
        for f in result.get("files", []) or []:
            items.append(
                {
                    "file_id": f.get("id"),
                    "name": f.get("name", ""),
                    "mime_type": f.get("mimeType", ""),
                    "modified_time": f.get("modifiedTime"),
                    "size": f.get("size"),
                    "web_link": f.get("webViewLink"),
                }
            )
        return {"items": items, "output": f"{len(items)} file(s) for `{q}`"}

    return per_account_fanout(account_label, _one)


def create_file(
    account_label: str,
    name: str,
    content: str = "",
    mime_type: str = "text/plain",
    parent_folder_id: str = "",
) -> dict[str, Any]:
    if not name:
        return {"ok": False, "output": "name is required", "error": "missing_name"}

    def _one(account: GoogleAccount) -> dict[str, Any]:
        from googleapiclient.http import MediaIoBaseUpload  # type: ignore[import-not-found]

        service = drive_client(account)
        body: dict[str, Any] = {"name": name, "mimeType": mime_type}
        if parent_folder_id:
            body["parents"] = [parent_folder_id]
        media = MediaIoBaseUpload(io.BytesIO(content.encode("utf-8")), mimetype=mime_type)
        f = (
            service.files()
            .create(body=body, media_body=media, fields="id,name,webViewLink")
            .execute()
        )
        return {
            "output": f"created {f.get('name')} ({f.get('webViewLink')})",
            "structured": {"file_id": f.get("id"), "web_link": f.get("webViewLink")},
        }

    return single_account(account_label, _one)


def update_file(
    account_label: str,
    file_id: str,
    content: str = "",
    name: str = "",
    mime_type: str = "text/plain",
) -> dict[str, Any]:
    if not file_id:
        return {"ok": False, "output": "file_id is required", "error": "missing_file_id"}

    def _one(account: GoogleAccount) -> dict[str, Any]:
        from googleapiclient.http import MediaIoBaseUpload  # type: ignore[import-not-found]

        service = drive_client(account)
        body: dict[str, Any] = {}
        if name:
            body["name"] = name
        kwargs: dict[str, Any] = {"fileId": file_id, "fields": "id,name,webViewLink"}
        if body:
            kwargs["body"] = body
        if content:
            kwargs["media_body"] = MediaIoBaseUpload(
                io.BytesIO(content.encode("utf-8")), mimetype=mime_type
            )
        if "body" not in kwargs and "media_body" not in kwargs:
            return {"ok": False, "output": "nothing to update", "error": "empty_patch"}
        f = service.files().update(**kwargs).execute()
        return {
            "output": f"updated {f.get('name')}",
            "structured": {"file_id": f.get("id"), "web_link": f.get("webViewLink")},
        }

    return single_account(account_label, _one)


def delete_file(account_label: str, file_id: str) -> dict[str, Any]:
    if not file_id:
        return {"ok": False, "output": "file_id is required", "error": "missing_file_id"}

    def _one(account: GoogleAccount) -> dict[str, Any]:
        service = drive_client(account)
        service.files().delete(fileId=file_id).execute()
        return {"output": f"deleted file {file_id}", "structured": {"file_id": file_id}}

    return single_account(account_label, _one)


def register() -> None:
    register_tool(ToolDefinition(
        id="google.drive.search_files",
        callable=search_files,
        description=(
            "Search Drive files. Scope is drive.file: only files this app "
            "created or that were shared with it. Args: account_label, query "
            "(Drive query syntax), limit."
        ),
    ))
    register_tool(ToolDefinition(
        id="google.drive.create_file",
        callable=create_file,
        description=(
            "Create a Drive file with raw text content. Args: account_label, "
            "name, content, mime_type (default 'text/plain'), parent_folder_id."
        ),
        approval_required=True,
    ))
    register_tool(ToolDefinition(
        id="google.drive.update_file",
        callable=update_file,
        description=(
            "Update a Drive file's name or contents. Args: account_label, "
            "file_id, content, name, mime_type."
        ),
        approval_required=True,
    ))
    register_tool(ToolDefinition(
        id="google.drive.delete_file",
        callable=delete_file,
        description="Delete a Drive file. Args: account_label, file_id.",
        approval_required=True,
    ))
