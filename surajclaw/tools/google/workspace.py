"""Google Workspace tools backed by the existing OAuth account store."""
from __future__ import annotations

from typing import Any

from agents.types import ToolDefinition
from tools.registry import register_tool


def _service(account_label: str, name: str, version: str):
    from core.google_accounts import get_account
    from googleapiclient.discovery import build  # type: ignore[import-not-found]

    account = get_account(account_label)
    return build(name, version, credentials=account.load_credentials(), cache_discovery=False)


def list_accounts() -> dict:
    from core.google_accounts import list_accounts as _list_accounts

    labels = [account.label for account in _list_accounts()]
    return {"ok": True, "output": "accounts: " + ", ".join(labels), "structured": {"accounts": labels}}


def gmail_search_messages(account_label: str, query: str = "", limit: int = 10) -> dict:
    service = _service(account_label, "gmail", "v1")
    response = service.users().messages().list(userId="me", q=query, maxResults=limit).execute()
    messages = response.get("messages", [])
    return {"ok": True, "output": f"Found {len(messages)} Gmail messages.", "structured": {"messages": messages}}


def gmail_get_message(account_label: str, message_id: str) -> dict:
    service = _service(account_label, "gmail", "v1")
    message = service.users().messages().get(userId="me", id=message_id, format="full").execute()
    return {"ok": True, "output": message.get("snippet", ""), "structured": {"message": message}}


def gmail_list_threads(account_label: str, query: str = "", limit: int = 10) -> dict:
    service = _service(account_label, "gmail", "v1")
    response = service.users().threads().list(userId="me", q=query, maxResults=limit).execute()
    threads = response.get("threads", [])
    return {"ok": True, "output": f"Found {len(threads)} Gmail threads.", "structured": {"threads": threads}}


def calendar_list_events(account_label: str, query: str = "", limit: int = 10) -> dict:
    service = _service(account_label, "calendar", "v3")
    events = service.events().list(calendarId="primary", q=query or None, maxResults=limit, singleEvents=True).execute().get("items", [])
    return {"ok": True, "output": f"Found {len(events)} calendar events.", "structured": {"events": events}}


def calendar_create_event(account_label: str, summary: str, start: dict | None = None, end: dict | None = None) -> dict:
    service = _service(account_label, "calendar", "v3")
    body = {"summary": summary}
    if start and end:
        body.update({"start": start, "end": end})
    event = service.events().insert(calendarId="primary", body=body).execute()
    return {"ok": True, "output": f"Created calendar event {event.get('id')}", "structured": {"event": event}}


def calendar_update_event(account_label: str, event_id: str, summary: str | None = None, patch: dict | None = None) -> dict:
    service = _service(account_label, "calendar", "v3")
    body = patch or {}
    if summary:
        body["summary"] = summary
    event = service.events().patch(calendarId="primary", eventId=event_id, body=body).execute()
    return {"ok": True, "output": f"Updated calendar event {event.get('id')}", "structured": {"event": event}}


def calendar_delete_event(account_label: str, event_id: str) -> dict:
    _service(account_label, "calendar", "v3").events().delete(calendarId="primary", eventId=event_id).execute()
    return {"ok": True, "output": f"Deleted calendar event {event_id}"}


def tasks_list_tasklists(account_label: str) -> dict:
    lists = _service(account_label, "tasks", "v1").tasklists().list().execute().get("items", [])
    return {"ok": True, "output": f"Found {len(lists)} task lists.", "structured": {"tasklists": lists}}


def tasks_list_tasks(account_label: str, tasklist_id: str = "@default", limit: int = 10) -> dict:
    tasks = _service(account_label, "tasks", "v1").tasks().list(tasklist=tasklist_id, maxResults=limit).execute().get("items", [])
    return {"ok": True, "output": f"Found {len(tasks)} tasks.", "structured": {"tasks": tasks}}


def tasks_create_task(account_label: str, title: str, tasklist_id: str = "@default") -> dict:
    task = _service(account_label, "tasks", "v1").tasks().insert(tasklist=tasklist_id, body={"title": title}).execute()
    return {"ok": True, "output": f"Created task {task.get('id')}", "structured": {"task": task}}


def tasks_update_task(account_label: str, task_id: str, title: str | None = None, tasklist_id: str = "@default", patch: dict | None = None) -> dict:
    body = patch or {}
    if title:
        body["title"] = title
    task = _service(account_label, "tasks", "v1").tasks().patch(tasklist=tasklist_id, task=task_id, body=body).execute()
    return {"ok": True, "output": f"Updated task {task.get('id')}", "structured": {"task": task}}


def tasks_delete_task(account_label: str, task_id: str, tasklist_id: str = "@default") -> dict:
    _service(account_label, "tasks", "v1").tasks().delete(tasklist=tasklist_id, task=task_id).execute()
    return {"ok": True, "output": f"Deleted task {task_id}"}


def drive_search_files(account_label: str, query: str = "", limit: int = 10) -> dict:
    q = query or "trashed = false"
    files = _service(account_label, "drive", "v3").files().list(q=q, pageSize=limit, fields="files(id,name,mimeType,webViewLink)").execute().get("files", [])
    return {"ok": True, "output": f"Found {len(files)} Drive files.", "structured": {"files": files}}


def drive_create_file(account_label: str, name: str, mime_type: str = "text/plain", content: str = "") -> dict:
    from googleapiclient.http import MediaInMemoryUpload  # type: ignore[import-not-found]

    media = MediaInMemoryUpload(content.encode(), mimetype=mime_type, resumable=False)
    file = _service(account_label, "drive", "v3").files().create(body={"name": name, "mimeType": mime_type}, media_body=media, fields="id,name,webViewLink").execute()
    return {"ok": True, "output": f"Created Drive file {file.get('id')}", "structured": {"file": file}}


def drive_update_file(account_label: str, file_id: str, name: str | None = None, content: str | None = None) -> dict:
    kwargs: dict[str, Any] = {"fileId": file_id, "fields": "id,name,webViewLink"}
    body = {"name": name} if name else None
    if content is not None:
        from googleapiclient.http import MediaInMemoryUpload  # type: ignore[import-not-found]

        kwargs["media_body"] = MediaInMemoryUpload(content.encode(), mimetype="text/plain", resumable=False)
    file = _service(account_label, "drive", "v3").files().update(body=body, **kwargs).execute()
    return {"ok": True, "output": f"Updated Drive file {file.get('id')}", "structured": {"file": file}}


def drive_delete_file(account_label: str, file_id: str) -> dict:
    _service(account_label, "drive", "v3").files().delete(fileId=file_id).execute()
    return {"ok": True, "output": f"Deleted Drive file {file_id}"}


def docs_create_doc(account_label: str, title: str) -> dict:
    doc = _service(account_label, "docs", "v1").documents().create(body={"title": title}).execute()
    return {"ok": True, "output": f"Created doc {doc.get('documentId')}", "structured": {"document": doc}}


def docs_append_text(account_label: str, document_id: str, text: str) -> dict:
    requests = [{"insertText": {"location": {"index": 1}, "text": text}}]
    result = _service(account_label, "docs", "v1").documents().batchUpdate(documentId=document_id, body={"requests": requests}).execute()
    return {"ok": True, "output": f"Updated doc {document_id}", "structured": {"result": result}}


def docs_replace_text(account_label: str, document_id: str, old_text: str, new_text: str) -> dict:
    requests = [{"replaceAllText": {"containsText": {"text": old_text, "matchCase": True}, "replaceText": new_text}}]
    result = _service(account_label, "docs", "v1").documents().batchUpdate(documentId=document_id, body={"requests": requests}).execute()
    return {"ok": True, "output": f"Replaced text in doc {document_id}", "structured": {"result": result}}


def docs_delete_doc(account_label: str, document_id: str) -> dict:
    return drive_delete_file(account_label, document_id)


def sheets_create_sheet(account_label: str, title: str) -> dict:
    sheet = _service(account_label, "sheets", "v4").spreadsheets().create(body={"properties": {"title": title}}).execute()
    return {"ok": True, "output": f"Created sheet {sheet.get('spreadsheetId')}", "structured": {"spreadsheet": sheet}}


def sheets_update_values(account_label: str, spreadsheet_id: str, values: list[list[Any]], range_name: str = "A1") -> dict:
    result = _service(account_label, "sheets", "v4").spreadsheets().values().update(spreadsheetId=spreadsheet_id, range=range_name, valueInputOption="USER_ENTERED", body={"values": values}).execute()
    return {"ok": True, "output": f"Updated sheet {spreadsheet_id}", "structured": {"result": result}}


def sheets_append_values(account_label: str, spreadsheet_id: str, values: list[list[Any]], range_name: str = "A1") -> dict:
    result = _service(account_label, "sheets", "v4").spreadsheets().values().append(spreadsheetId=spreadsheet_id, range=range_name, valueInputOption="USER_ENTERED", body={"values": values}).execute()
    return {"ok": True, "output": f"Appended values to sheet {spreadsheet_id}", "structured": {"result": result}}


def sheets_delete_sheet(account_label: str, spreadsheet_id: str) -> dict:
    return drive_delete_file(account_label, spreadsheet_id)


def contacts_search(account_label: str, query: str = "", limit: int = 10) -> dict:
    service = _service(account_label, "people", "v1")
    response = service.people().searchContacts(query=query, readMask="names,emailAddresses", pageSize=limit).execute()
    results = response.get("results", [])
    return {"ok": True, "output": f"Found {len(results)} contacts.", "structured": {"results": results}}


for _id, _fn, _desc, _approval in (
    ("google.accounts.list", list_accounts, "List connected Google accounts.", False),
    ("google.gmail.search_messages", gmail_search_messages, "Search Gmail messages read-only.", False),
    ("google.gmail.get_message", gmail_get_message, "Read one Gmail message.", False),
    ("google.gmail.list_threads", gmail_list_threads, "List Gmail threads read-only.", False),
    ("google.calendar.list_events", calendar_list_events, "List calendar events.", False),
    ("google.calendar.create_event", calendar_create_event, "Create calendar event.", False),
    ("google.calendar.update_event", calendar_update_event, "Update calendar event.", False),
    ("google.calendar.delete_event", calendar_delete_event, "Delete calendar event.", True),
    ("google.tasks.list_tasklists", tasks_list_tasklists, "List task lists.", False),
    ("google.tasks.list_tasks", tasks_list_tasks, "List tasks.", False),
    ("google.tasks.create_task", tasks_create_task, "Create task.", False),
    ("google.tasks.update_task", tasks_update_task, "Update task.", False),
    ("google.tasks.delete_task", tasks_delete_task, "Delete task.", True),
    ("google.drive.search_files", drive_search_files, "Search Drive files.", False),
    ("google.drive.create_file", drive_create_file, "Create Drive file.", False),
    ("google.drive.update_file", drive_update_file, "Update Drive file.", False),
    ("google.drive.delete_file", drive_delete_file, "Delete Drive file.", True),
    ("google.docs.create_doc", docs_create_doc, "Create Google Doc.", False),
    ("google.docs.append_text", docs_append_text, "Append text to Google Doc.", False),
    ("google.docs.replace_text", docs_replace_text, "Replace text in Google Doc.", False),
    ("google.docs.delete_doc", docs_delete_doc, "Delete Google Doc.", True),
    ("google.sheets.create_sheet", sheets_create_sheet, "Create Google Sheet.", False),
    ("google.sheets.update_values", sheets_update_values, "Update Google Sheet values.", False),
    ("google.sheets.append_values", sheets_append_values, "Append Google Sheet values.", False),
    ("google.sheets.delete_sheet", sheets_delete_sheet, "Delete Google Sheet.", True),
    ("google.contacts.search", contacts_search, "Search contacts read-only.", False),
):
    register_tool(ToolDefinition(_id, _fn, _desc, risk_level="high" if _approval else "low", approval_required=_approval))
