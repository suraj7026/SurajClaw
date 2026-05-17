"""Shared helpers for Google Workspace tools.

Every Google tool takes ``account_label`` and may operate against one or all
connected accounts. This module centralizes:

* Loading credentials from ``core.google_accounts``.
* Building per-service API clients with the Google Python client lib.
* Fan-out across all accounts when ``account_label == "all"``.
* A uniform error / structured-output shape so downstream LLMs can iterate.
"""
from __future__ import annotations

from typing import Any, Callable, Iterable

from core.google_accounts import GoogleAccount, get_account, list_accounts


def _build(service: str, version: str, account: GoogleAccount):
    """Construct a googleapiclient.discovery Resource for ``account``.

    Lazy import keeps Google libs out of the import path for non-Google flows.
    """
    from googleapiclient.discovery import build  # type: ignore[import-not-found]

    creds = account.load_credentials()
    return build(service, version, credentials=creds, cache_discovery=False)


def gmail_client(account: GoogleAccount):
    return _build("gmail", "v1", account)


def calendar_client(account: GoogleAccount):
    return _build("calendar", "v3", account)


def tasks_client(account: GoogleAccount):
    return _build("tasks", "v1", account)


def drive_client(account: GoogleAccount):
    return _build("drive", "v3", account)


def docs_client(account: GoogleAccount):
    return _build("docs", "v1", account)


def sheets_client(account: GoogleAccount):
    return _build("sheets", "v4", account)


def people_client(account: GoogleAccount):
    return _build("people", "v1", account)


def resolve_accounts(account_label: str) -> list[GoogleAccount]:
    """Return [account] for a label, or every connected account for ``"all"``."""
    label = (account_label or "").strip()
    if not label:
        raise ValueError("account_label is required")
    if label == "all":
        accounts = list_accounts()
        if not accounts:
            raise LookupError("no Google accounts connected")
        return accounts
    return [get_account(label)]


def per_account_fanout(
    account_label: str,
    fn: Callable[[GoogleAccount], dict[str, Any]],
) -> dict[str, Any]:
    """Call ``fn`` for each resolved account, merge results.

    ``fn`` returns ``{"items": [...], "output": "..."}``. We tag each item with
    ``account_label`` and concatenate ``output`` lines.
    """
    try:
        accounts = resolve_accounts(account_label)
    except (ValueError, LookupError) as exc:
        return {"ok": False, "output": str(exc), "error": "account_lookup_failed"}

    merged_items: list[dict[str, Any]] = []
    summaries: list[str] = []
    errors: list[str] = []
    for account in accounts:
        try:
            result = fn(account)
        except Exception as exc:  # noqa: BLE001 -- per-account isolation
            errors.append(f"{account.label}: {exc}")
            continue
        for item in result.get("items", []) or []:
            if isinstance(item, dict):
                item.setdefault("account_label", account.label)
            merged_items.append(item)
        if result.get("output"):
            summaries.append(f"[{account.label}] {result['output']}")

    return {
        "ok": True,
        "output": "\n".join(summaries) if summaries else "no results",
        "structured": {"items": merged_items, "errors": errors},
    }


def single_account(
    account_label: str,
    fn: Callable[[GoogleAccount], dict[str, Any]],
) -> dict[str, Any]:
    """Resolve a single account (no ``"all"``) and run ``fn``.

    Used by write tools that need an unambiguous target.
    """
    label = (account_label or "").strip()
    if label == "all":
        return {
            "ok": False,
            "output": "account_label='all' is not valid for write tools; pick one account",
            "error": "ambiguous_account",
        }
    try:
        account = get_account(label)
    except LookupError as exc:
        return {"ok": False, "output": str(exc), "error": "unknown_account"}
    try:
        result = fn(account)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "output": f"{type(exc).__name__}: {exc}", "error": type(exc).__name__}
    if "ok" not in result:
        result["ok"] = True
    structured = result.setdefault("structured", {})
    structured.setdefault("account_label", account.label)
    return result


def truncate(text: str, limit: int = 500) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def iter_messages(executor: Any, request: Any) -> Iterable[Any]:
    """Iterate pages from a Google API list() / list_next() pair."""
    response = request.execute()
    while response is not None:
        yield response
        request = executor.list_next(request, response)
        if request is None:
            break
        response = request.execute()
