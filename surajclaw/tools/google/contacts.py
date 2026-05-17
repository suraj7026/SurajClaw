"""Google Contacts tools (read-only — contacts.readonly scope)."""
from __future__ import annotations

from typing import Any

from agents.types import ToolDefinition
from core.google_accounts import GoogleAccount
from tools.google._common import people_client, per_account_fanout
from tools.registry import register_tool


def search_contacts(
    account_label: str = "all",
    query: str = "",
    limit: int = 20,
) -> dict[str, Any]:
    if not query:
        return {"ok": False, "output": "query is required", "error": "missing_query"}

    def _one(account: GoogleAccount) -> dict[str, Any]:
        service = people_client(account)
        # warmup call required by People API for searchContacts to return results
        service.people().searchContacts(query="", readMask="names").execute()
        result = (
            service.people()
            .searchContacts(
                query=query,
                pageSize=max(1, min(limit, 30)),
                readMask="names,emailAddresses,phoneNumbers,organizations",
            )
            .execute()
        )
        items = []
        for entry in result.get("results", []) or []:
            person = entry.get("person", {}) or {}
            names = person.get("names") or []
            primary_name = names[0].get("displayName") if names else ""
            emails = [e.get("value", "") for e in (person.get("emailAddresses") or [])]
            phones = [p.get("value", "") for p in (person.get("phoneNumbers") or [])]
            orgs = [o.get("name", "") for o in (person.get("organizations") or [])]
            items.append(
                {
                    "name": primary_name,
                    "emails": emails,
                    "phones": phones,
                    "organizations": orgs,
                }
            )
        return {"items": items, "output": f"{len(items)} contact(s) for `{query}`"}

    return per_account_fanout(account_label, _one)


def register() -> None:
    register_tool(ToolDefinition(
        id="google.contacts.search",
        callable=search_contacts,
        description=(
            "Search Google Contacts (read-only). Args: account_label, query, "
            "limit. Returns name, emails, phones, organizations per match."
        ),
    ))
