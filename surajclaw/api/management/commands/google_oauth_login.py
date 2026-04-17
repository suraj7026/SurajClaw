"""One-time Google OAuth flow (supports multiple accounts).

Reads ``GOOGLE_CLIENT_SECRETS_PATH`` (web/installed OAuth client JSON), runs
the auth flow against a loopback redirect, and writes the resulting
refresh-token credentials to ``{GOOGLE_TOKEN_DIR}/{account}.json``.

Usage:

    python manage.py google_oauth_login --account personal
    python manage.py google_oauth_login --account work
    python manage.py google_oauth_login                 # uses --account default
    python manage.py google_oauth_login --port 8090 --no-browser

If you see ``redirect_uri_mismatch``, add ``http://localhost:<port>/`` to your
OAuth client's "Authorized redirect URIs" in Google Cloud Console (or convert
the client to type "Desktop", which auto-allows loopback).
"""
from __future__ import annotations

import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.google_accounts import list_accounts, path_for, validate_label

# These scopes match what the bundled tools/ask for. Add/remove here, then
# re-run the command; the token file will be regenerated.
DEFAULT_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/tasks",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/contacts.readonly",
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
]


class Command(BaseCommand):
    help = "Run the Google OAuth flow and persist a refresh token."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--account",
            type=str,
            default="default",
            help=(
                "Short slug identifying this Google account on disk "
                "(stored as <GOOGLE_TOKEN_DIR>/<account>.json). "
                "Examples: personal, work. Default: default."
            ),
        )
        parser.add_argument(
            "--port",
            type=int,
            default=8090,
            help="Loopback port to receive the OAuth redirect (default 8090).",
        )
        parser.add_argument(
            "--no-browser",
            action="store_true",
            help="Print the auth URL instead of trying to open a browser.",
        )
        parser.add_argument(
            "--scope",
            action="append",
            default=None,
            help=(
                "Repeatable; override DEFAULT_SCOPES. Example: "
                "--scope https://www.googleapis.com/auth/gmail.readonly"
            ),
        )

    def handle(self, *_args, **opts) -> None:
        try:
            from google_auth_oauthlib.flow import InstalledAppFlow  # type: ignore[import-not-found]
        except ImportError as exc:
            raise CommandError(
                "google-auth-oauthlib is not installed. Run `pip install -r requirements.txt`."
            ) from exc

        secrets_path = Path(settings.GOOGLE_CLIENT_SECRETS_PATH)
        if not secrets_path.exists():
            raise CommandError(
                f"Client secrets not found at {secrets_path}. Set GOOGLE_CLIENT_SECRETS_PATH."
            )

        try:
            account = validate_label(opts["account"])
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        token_path = path_for(account)
        token_path.parent.mkdir(parents=True, exist_ok=True)

        scopes = opts["scope"] or DEFAULT_SCOPES
        port = opts["port"]
        open_browser = not opts["no_browser"]

        self.stdout.write(self.style.NOTICE(f"Using scopes:\n  - " + "\n  - ".join(scopes)))
        self.stdout.write(
            self.style.WARNING(
                f"\nIf you see redirect_uri_mismatch, add http://localhost:{port}/ "
                "to your OAuth client's Authorized redirect URIs."
            )
        )

        flow = InstalledAppFlow.from_client_secrets_file(str(secrets_path), scopes=scopes)
        # `access_type=offline` + `prompt=consent` guarantees we get a refresh
        # token (without it Google may return only an access token on repeat
        # consents, breaking the long-lived watcher task).
        creds = flow.run_local_server(
            port=port,
            open_browser=open_browser,
            authorization_prompt_message=(
                "Visit this URL to authorize SurajClaw: {url}"
            ),
            access_type="offline",
            prompt="consent",
        )

        token_path.write_text(creds.to_json(), encoding="utf-8")
        # Surface the email so the operator can confirm they signed in as the
        # intended account.
        try:
            from googleapiclient.discovery import build  # type: ignore[import-not-found]

            userinfo = (
                build("oauth2", "v2", credentials=creds, cache_discovery=False)
                .userinfo()
                .get()
                .execute()
            )
            email = userinfo.get("email", "(unknown)")
        except Exception:  # noqa: BLE001 -- best-effort label only
            email = "(could not read userinfo)"

        self.stdout.write(
            self.style.SUCCESS(
                f"\nWrote token for account '{account}' -> {token_path}\n"
                f"Signed in as: {email}\n"
                f"Granted scopes: {len(creds.scopes or scopes)}\n"
            )
        )
        # Show every account that's now on disk so it's obvious when you're
        # managing more than one Gmail login.
        known = [a.label for a in list_accounts()]
        self.stdout.write(
            self.style.NOTICE(f"Connected accounts ({len(known)}): {', '.join(known) or '(none)'}")
        )
        # Also print a tiny summary that's safe to show in chat.
        self.stdout.write(
            json.dumps({"account": account, "token_path": str(token_path), "email": email})
        )
