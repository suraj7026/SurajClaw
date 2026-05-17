"""``python manage.py gemini_login`` -- OAuth-login into Google AI / Gemini.

After this completes, every agent turn routes through the OAuth-backed
``gemini-cli`` provider (Code Assist endpoint) using your Google AI Pro
quota.

Subcommands:

    gemini_login              -- run the OAuth flow (opens a browser)
    gemini_login status       -- show stored credentials + project
    gemini_login reonboard    -- re-detect Code Assist tier (use after
                                 upgrading from free to Google AI Pro)
    gemini_login logout       -- delete the stored token file
"""
from __future__ import annotations

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Sign in to Google AI / Gemini via OAuth (uses your subscription)."

    def add_arguments(self, parser):
        sub = parser.add_subparsers(dest="action")
        sub.add_parser("status")
        sub.add_parser("logout")
        login = sub.add_parser("login")
        login.add_argument("--no-browser", action="store_true")
        login.add_argument("--port", type=int, default=0)
        ro = sub.add_parser("reonboard", help="Re-detect Code Assist tier + project")
        ro.add_argument(
            "--tier",
            default="",
            help="Force a specific tier id (legacy-tier, standard-tier, free-tier).",
        )

    def handle(self, *args, **opts):
        from agents.gemini_oauth import (
            clear_credentials,
            load_credentials,
            onboard_project,
            save_credentials,
            surajclaw_gemini_login,
        )

        action = opts.get("action") or "login"

        if action == "status":
            creds = load_credentials()
            if creds is None:
                self.stdout.write("no gemini credentials saved")
                return
            self.stdout.write(f"email:      {creds.email or '(unknown)'}")
            self.stdout.write(
                f"project_id: {creds.project_id or '(none — will resolve on first call)'}"
            )
            self.stdout.write(
                "access:     " + ("EXPIRED" if creds.is_expired() else "valid")
            )
            return

        if action == "logout":
            if clear_credentials():
                self.stdout.write(self.style.SUCCESS("cleared gemini credentials"))
            else:
                self.stdout.write("no credentials to clear")
            return

        if action == "reonboard":
            creds = load_credentials()
            if creds is None:
                self.stdout.write(
                    self.style.ERROR(
                        "no credentials — run `manage.py gemini_login` first."
                    )
                )
                return
            tier = opts.get("tier") or ""
            if tier:
                import os

                os.environ["SURAJCLAW_GEMINI_TIER"] = tier
                self.stdout.write(f"forcing tier_id={tier!r}")
            # Drop the cached project_id so onboard re-runs.
            creds.project_id = ""
            save_credentials(creds)
            try:
                project = onboard_project(force=True)
            except Exception as exc:  # noqa: BLE001
                self.stdout.write(self.style.ERROR(f"reonboard failed: {exc}"))
                return
            self.stdout.write(self.style.SUCCESS(f"reonboarded; project_id={project}"))
            return

        # default action: login
        creds = surajclaw_gemini_login(
            open_browser=not opts.get("no_browser"),
            port=int(opts.get("port") or 0),
        )
        self.stdout.write(self.style.SUCCESS(f"signed in as {creds.email}"))
        try:
            project = onboard_project()
            self.stdout.write(f"project_id: {project}")
        except Exception as exc:  # noqa: BLE001
            self.stdout.write(
                self.style.WARNING(
                    f"could not auto-resolve a Code Assist project: {exc}.\n"
                    "Set SURAJCLAW_GEMINI_PROJECT_ID in .env if Gemini calls fail."
                )
            )
