"""Google Docs tools."""
from __future__ import annotations

from typing import Any

from agents.types import ToolDefinition
from core.google_accounts import GoogleAccount
from tools.google._common import docs_client, drive_client, single_account
from tools.registry import register_tool


def create_doc(
    account_label: str,
    title: str,
    body: str = "",
) -> dict[str, Any]:
    if not title:
        return {"ok": False, "output": "title is required", "error": "missing_title"}

    def _one(account: GoogleAccount) -> dict[str, Any]:
        docs = docs_client(account)
        doc = docs.documents().create(body={"title": title}).execute()
        doc_id = doc.get("documentId")
        if body:
            docs.documents().batchUpdate(
                documentId=doc_id,
                body={"requests": [{"insertText": {"location": {"index": 1}, "text": body}}]},
            ).execute()
        web_link = f"https://docs.google.com/document/d/{doc_id}/edit"
        return {
            "output": f"created '{title}' ({web_link})",
            "structured": {"document_id": doc_id, "web_link": web_link},
        }

    return single_account(account_label, _one)


def _end_index(doc: dict[str, Any]) -> int:
    """Return the document's last index for safe append insertions."""
    body = doc.get("body") or {}
    content = body.get("content") or []
    if not content:
        return 1
    last = content[-1]
    return int(last.get("endIndex", 1)) - 1 or 1


def append_text(
    account_label: str,
    document_id: str,
    text: str,
) -> dict[str, Any]:
    if not document_id or not text:
        return {"ok": False, "output": "document_id and text are required", "error": "missing_args"}

    def _one(account: GoogleAccount) -> dict[str, Any]:
        docs = docs_client(account)
        doc = docs.documents().get(documentId=document_id).execute()
        index = _end_index(doc)
        docs.documents().batchUpdate(
            documentId=document_id,
            body={"requests": [{"insertText": {"location": {"index": index}, "text": text}}]},
        ).execute()
        return {
            "output": f"appended {len(text)} chars to {document_id}",
            "structured": {"document_id": document_id, "appended_chars": len(text)},
        }

    return single_account(account_label, _one)


def replace_text(
    account_label: str,
    document_id: str,
    find: str,
    replace: str,
    match_case: bool = False,
) -> dict[str, Any]:
    if not document_id or not find:
        return {"ok": False, "output": "document_id and find are required", "error": "missing_args"}

    def _one(account: GoogleAccount) -> dict[str, Any]:
        docs = docs_client(account)
        docs.documents().batchUpdate(
            documentId=document_id,
            body={
                "requests": [
                    {
                        "replaceAllText": {
                            "containsText": {"text": find, "matchCase": match_case},
                            "replaceText": replace,
                        }
                    }
                ]
            },
        ).execute()
        return {
            "output": f"replaced '{find}' with '{replace}' in {document_id}",
            "structured": {"document_id": document_id},
        }

    return single_account(account_label, _one)


def delete_doc(account_label: str, document_id: str) -> dict[str, Any]:
    if not document_id:
        return {"ok": False, "output": "document_id is required", "error": "missing_document_id"}

    def _one(account: GoogleAccount) -> dict[str, Any]:
        drive = drive_client(account)
        drive.files().delete(fileId=document_id).execute()
        return {"output": f"deleted doc {document_id}", "structured": {"document_id": document_id}}

    return single_account(account_label, _one)


def register() -> None:
    register_tool(ToolDefinition(
        id="google.docs.create_doc",
        callable=create_doc,
        description=(
            "Create a new Google Doc with optional initial body text. Args: "
            "account_label (single), title, body."
        ),
        approval_required=True,
    ))
    register_tool(ToolDefinition(
        id="google.docs.append_text",
        callable=append_text,
        description=(
            "Append text to an existing Google Doc. Args: account_label, "
            "document_id, text."
        ),
        approval_required=True,
    ))
    register_tool(ToolDefinition(
        id="google.docs.replace_text",
        callable=replace_text,
        description=(
            "Replace all occurrences of `find` with `replace` in a Doc. Args: "
            "account_label, document_id, find, replace, match_case."
        ),
        approval_required=True,
    ))
    register_tool(ToolDefinition(
        id="google.docs.delete_doc",
        callable=delete_doc,
        description="Delete a Google Doc. Args: account_label, document_id.",
        approval_required=True,
    ))
