"""``python manage.py codeassist_status`` -- diagnose OAuth auth state.

Reports on the three OAuth flows SurajClaw relies on:

1. **gemini auth** (chat agent)        -- token under ``google_tokens/gemini_oauth.json``
2. **gemini cli codeassist auth**      -- host ``~/.gemini/`` populated by ``gemini auth login``
3. **antigravity auth**                -- host ``~/.config/antigravity/`` populated by ``antigravity auth login``

For each it prints the path it's looking at, whether it exists, and the
freshness (mtime). No tokens are printed.
"""
from __future__ import annotations

import datetime as dt
import os
import shutil
from pathlib import Path

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Show which Google OAuth flows are live on this host."

    def handle(self, *args, **opts):
        rows = []

        # 1. gemini chat agent OAuth (manage.py gemini_login)
        from agents.gemini_oauth import load_credentials as load_gemini

        gemini_path = Path("google_tokens/gemini_oauth.json")
        gemini_creds = load_gemini()
        rows.append((
            "gemini auth (chat agent)",
            "manage.py gemini_login",
            gemini_path,
            gemini_creds is not None,
            (
                f"email={gemini_creds.email or '?'} expired={gemini_creds.is_expired()}"
                if gemini_creds
                else "not signed in"
            ),
        ))

        # 2. gemini CLI codeassist auth (upstream `gemini auth login`)
        gemini_cli_dir = Path(os.environ.get("GEMINI_HOST_AUTH_DIR", str(Path.home() / ".gemini")))
        rows.append((
            "gemini cli codeassist auth",
            "gemini auth login (host)",
            gemini_cli_dir,
            gemini_cli_dir.exists(),
            _dir_stats(gemini_cli_dir),
        ))

        # 3. antigravity auth (upstream `antigravity auth login`)
        ag_dir = Path(
            os.environ.get(
                "ANTIGRAVITY_HOST_AUTH_DIR",
                str(Path.home() / ".config" / "antigravity"),
            )
        )
        rows.append((
            "antigravity auth",
            "antigravity auth login (host)",
            ag_dir,
            ag_dir.exists(),
            _dir_stats(ag_dir),
        ))

        # Bonus: are the upstream CLIs even installed?
        rows.append((
            "gemini binary",
            "npm i -g @google/gemini-cli",
            shutil.which("gemini") or "(not on PATH)",
            shutil.which("gemini") is not None,
            "",
        ))
        rows.append((
            "antigravity binary",
            "see Antigravity install docs",
            shutil.which("antigravity") or "(not on PATH)",
            shutil.which("antigravity") is not None,
            "",
        ))

        # Render
        name_w = max(len(r[0]) for r in rows) + 2
        path_w = max(len(str(r[2])) for r in rows) + 2
        self.stdout.write("=" * (name_w + path_w + 24))
        self.stdout.write(
            f"{'auth flow':<{name_w}}{'how to set up':<32}{'path':<{path_w}}status"
        )
        self.stdout.write("-" * (name_w + path_w + 24))
        for name, howto, path, ok, detail in rows:
            mark = self.style.SUCCESS("ok") if ok else self.style.WARNING("missing")
            line = f"{name:<{name_w}}{howto:<32}{str(path):<{path_w}}{mark}"
            self.stdout.write(line)
            if detail:
                self.stdout.write(f"  └─ {detail}")


def _dir_stats(p: Path) -> str:
    if not p.exists():
        return ""
    try:
        files = list(p.rglob("*"))
        files = [f for f in files if f.is_file()]
        if not files:
            return "(empty)"
        newest = max(files, key=lambda f: f.stat().st_mtime)
        ts = dt.datetime.fromtimestamp(newest.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        return f"{len(files)} file(s), newest {newest.name} @ {ts}"
    except Exception as exc:  # noqa: BLE001
        return f"(stat failed: {exc})"
