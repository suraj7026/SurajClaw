"""Smoke test: list the most recent Gmail messages for one or all accounts.

Useful right after ``manage.py google_oauth_login --account <label>`` to
confirm the token works end-to-end.

Examples:

    # All connected accounts, 5 messages each
    python manage.py test_gmail

    # Just one account
    python manage.py test_gmail --account work --count 10

    # Apply a Gmail search query (same syntax as the web UI)
    python manage.py test_gmail --query "is:unread newer_than:1d"
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from core.google_accounts import GoogleAccount, get_account, list_accounts


class Command(BaseCommand):
    help = "List the N most recent Gmail headers per connected account (default 5)."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--account",
            type=str,
            default=None,
            help=(
                "Slug to test (matches <GOOGLE_TOKEN_DIR>/<slug>.json). "
                "Omit to iterate every connected account."
            ),
        )
        parser.add_argument("--count", type=int, default=5, help="How many messages to show.")
        parser.add_argument(
            "--query", type=str, default="", help="Gmail search query (e.g. 'from:me')."
        )

    def handle(self, *_args, **opts) -> None:
        try:
            from googleapiclient.discovery import build  # type: ignore[import-not-found]  # noqa: F401
        except ImportError as exc:
            raise CommandError("google api libs missing. `pip install -r requirements.txt`.") from exc

        if opts["account"]:
            try:
                accounts = [get_account(opts["account"])]
            except LookupError as exc:
                raise CommandError(str(exc)) from exc
        else:
            accounts = list_accounts()
            if not accounts:
                raise CommandError(
                    "No Google accounts connected. "
                    "Run: python manage.py google_oauth_login --account <label>"
                )

        for account in accounts:
            self._list_one(account, count=opts["count"], query=opts["query"])

    def _list_one(self, account: GoogleAccount, *, count: int, query: str) -> None:
        from googleapiclient.discovery import build  # type: ignore[import-not-found]

        creds = account.load_credentials(
            scopes=["https://www.googleapis.com/auth/gmail.readonly"],
        )
        gmail = build("gmail", "v1", credentials=creds, cache_discovery=False)

        self.stdout.write(self.style.MIGRATE_HEADING(f"\n== account: {account.label} =="))
        list_resp = (
            gmail.users()
            .messages()
            .list(userId="me", maxResults=count, q=query or None)
            .execute()
        )
        ids = [m["id"] for m in list_resp.get("messages", [])]
        if not ids:
            self.stdout.write(self.style.WARNING("  (no messages matched)"))
            return

        self.stdout.write(self.style.SUCCESS(f"  latest {len(ids)} message(s):"))
        for msg_id in ids:
            meta = (
                gmail.users()
                .messages()
                .get(
                    userId="me",
                    id=msg_id,
                    format="metadata",
                    metadataHeaders=["From", "Subject", "Date"],
                )
                .execute()
            )
            headers = {h["name"]: h["value"] for h in meta["payload"].get("headers", [])}
            self.stdout.write(
                f"  - [{headers.get('Date', '?')}] "
                f"{headers.get('From', '?')} :: {headers.get('Subject', '(no subject)')}"
            )
