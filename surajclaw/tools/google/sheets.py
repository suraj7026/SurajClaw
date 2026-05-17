"""Google Sheets tools."""
from __future__ import annotations

from typing import Any

from agents.types import ToolDefinition
from core.google_accounts import GoogleAccount
from tools.google._common import drive_client, sheets_client, single_account
from tools.registry import register_tool


def create_sheet(
    account_label: str,
    title: str,
    sheet_title: str = "Sheet1",
) -> dict[str, Any]:
    if not title:
        return {"ok": False, "output": "title is required", "error": "missing_title"}

    def _one(account: GoogleAccount) -> dict[str, Any]:
        sheets = sheets_client(account)
        body = {
            "properties": {"title": title},
            "sheets": [{"properties": {"title": sheet_title}}],
        }
        sheet = sheets.spreadsheets().create(body=body).execute()
        sid = sheet.get("spreadsheetId")
        web_link = f"https://docs.google.com/spreadsheets/d/{sid}/edit"
        return {
            "output": f"created '{title}' ({web_link})",
            "structured": {"spreadsheet_id": sid, "web_link": web_link},
        }

    return single_account(account_label, _one)


def update_values(
    account_label: str,
    spreadsheet_id: str,
    range_a1: str,
    values: list[list[Any]],
) -> dict[str, Any]:
    if not spreadsheet_id or not range_a1 or values is None:
        return {"ok": False, "output": "spreadsheet_id, range_a1, values are required", "error": "missing_args"}

    def _one(account: GoogleAccount) -> dict[str, Any]:
        sheets = sheets_client(account)
        result = (
            sheets.spreadsheets()
            .values()
            .update(
                spreadsheetId=spreadsheet_id,
                range=range_a1,
                valueInputOption="USER_ENTERED",
                body={"values": values},
            )
            .execute()
        )
        return {
            "output": f"updated {result.get('updatedCells', 0)} cell(s) in {range_a1}",
            "structured": result,
        }

    return single_account(account_label, _one)


def append_values(
    account_label: str,
    spreadsheet_id: str,
    range_a1: str,
    values: list[list[Any]],
) -> dict[str, Any]:
    if not spreadsheet_id or not range_a1 or values is None:
        return {"ok": False, "output": "spreadsheet_id, range_a1, values are required", "error": "missing_args"}

    def _one(account: GoogleAccount) -> dict[str, Any]:
        sheets = sheets_client(account)
        result = (
            sheets.spreadsheets()
            .values()
            .append(
                spreadsheetId=spreadsheet_id,
                range=range_a1,
                valueInputOption="USER_ENTERED",
                insertDataOption="INSERT_ROWS",
                body={"values": values},
            )
            .execute()
        )
        updates = result.get("updates") or {}
        return {
            "output": f"appended {updates.get('updatedCells', 0)} cell(s) to {range_a1}",
            "structured": result,
        }

    return single_account(account_label, _one)


def delete_sheet(account_label: str, spreadsheet_id: str) -> dict[str, Any]:
    if not spreadsheet_id:
        return {"ok": False, "output": "spreadsheet_id is required", "error": "missing_spreadsheet_id"}

    def _one(account: GoogleAccount) -> dict[str, Any]:
        drive = drive_client(account)
        drive.files().delete(fileId=spreadsheet_id).execute()
        return {
            "output": f"deleted spreadsheet {spreadsheet_id}",
            "structured": {"spreadsheet_id": spreadsheet_id},
        }

    return single_account(account_label, _one)


def register() -> None:
    register_tool(ToolDefinition(
        id="google.sheets.create_sheet",
        callable=create_sheet,
        description=(
            "Create a new spreadsheet. Args: account_label (single), title, "
            "sheet_title (the first tab's name)."
        ),
        approval_required=True,
    ))
    register_tool(ToolDefinition(
        id="google.sheets.update_values",
        callable=update_values,
        description=(
            "Overwrite a range with 2D values. Args: account_label, "
            "spreadsheet_id, range_a1 (e.g. 'Sheet1!A1:B3'), values (list of "
            "rows)."
        ),
        approval_required=True,
    ))
    register_tool(ToolDefinition(
        id="google.sheets.append_values",
        callable=append_values,
        description=(
            "Append rows to a sheet. Args: account_label, spreadsheet_id, "
            "range_a1 (table starting cell), values (list of rows)."
        ),
        approval_required=True,
    ))
    register_tool(ToolDefinition(
        id="google.sheets.delete_sheet",
        callable=delete_sheet,
        description="Delete a spreadsheet. Args: account_label, spreadsheet_id.",
        approval_required=True,
    ))
