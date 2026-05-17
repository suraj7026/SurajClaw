"""``surajclaw`` CLI entry point.

Subcommands:

* ``login``    — exchange username/password for a DRF token, persist it.
* ``logout``   — invalidate the stored token on the server and locally.
* ``whoami``   — print the authenticated user (or report not logged in).
* ``doctor``   — call ``GET /api/doctor/`` and pretty-print checks.
* ``status``   — short summary: server URL, user, /api/health/ ping.
* ``chat``     — open a WebSocket REPL against the agent backend.
* ``tui``      — open a full-screen Textual UI against the same backend.

All "power" features (slash commands, model directives, agent invocation)
are typed inline inside ``chat`` and dispatched server-side; the CLI does
not need per-command code for them.
"""
from __future__ import annotations

import argparse
import getpass
import json
import sys
from typing import Any

from rich.console import Console
from rich.table import Table

from clawcli import __version__
from clawcli.chat import run_chat_repl
from clawcli.tui import run_tui
from clawcli.config import (
    Credentials,
    DEFAULT_SERVER,
    clear_credentials,
    credentials_path,
    load_credentials,
    resolve_server,
    save_credentials,
)
from clawcli.http import ApiClient, ApiError


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    console = Console()
    handler = args.func  # set by sub-parsers
    try:
        return int(handler(args, console) or 0)
    except ApiError as exc:
        console.print(f"[bold red]error:[/] {exc}")
        return 1
    except KeyboardInterrupt:
        console.print()
        return 130


# ---------------------------------------------------------------------------
# parser
# ---------------------------------------------------------------------------
def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="surajclaw",
        description="Command-line interface for the SurajClaw personal AI backend.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"surajclaw {__version__}",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    p_login = sub.add_parser("login", help="Authenticate and store a token.")
    p_login.add_argument("--server", help=f"Backend URL (default: {DEFAULT_SERVER})")
    p_login.add_argument("--username", "-u", help="Username; prompted if omitted.")
    p_login.set_defaults(func=_cmd_login)

    p_logout = sub.add_parser("logout", help="Invalidate the stored token.")
    p_logout.set_defaults(func=_cmd_logout)

    p_whoami = sub.add_parser("whoami", help="Print the authenticated user.")
    p_whoami.set_defaults(func=_cmd_whoami)

    p_doctor = sub.add_parser("doctor", help="Run server-side health checks.")
    p_doctor.add_argument("--server", help="Override server URL.")
    p_doctor.set_defaults(func=_cmd_doctor)

    p_status = sub.add_parser("status", help="Summarize CLI + server health.")
    p_status.add_argument("--server", help="Override server URL.")
    p_status.set_defaults(func=_cmd_status)

    p_chat = sub.add_parser("chat", help="Open the chat REPL.")
    p_chat.add_argument("--server", help="Override server URL.")
    p_chat.add_argument("--session", help="Reuse a session UUID instead of generating one.")
    p_chat.add_argument(
        "--as",
        dest="as_id",
        help="Identify as <name> via the WS `?as=` allowlist (use with --no-auth).",
    )
    p_chat.add_argument(
        "--no-auth",
        action="store_true",
        help="Skip token auth (requires OWNER_ALLOW_FROM=web:* on the server).",
    )
    p_chat.add_argument(
        "--debug",
        action="store_true",
        help="Log every received frame's type/keys (useful for diagnosing hangs).",
    )
    p_chat.set_defaults(func=_cmd_chat)

    p_tui = sub.add_parser("tui", help="Open the full-screen Textual UI.")
    p_tui.add_argument("--server", help="Override server URL.")
    p_tui.add_argument("--session", help="Reuse a session UUID instead of generating one.")
    p_tui.add_argument(
        "--as",
        dest="as_id",
        help="Identify as <name> via the WS `?as=` allowlist (use with --no-auth).",
    )
    p_tui.add_argument(
        "--no-auth",
        action="store_true",
        help="Skip token auth (requires OWNER_ALLOW_FROM=web:* on the server).",
    )
    p_tui.add_argument(
        "--debug",
        action="store_true",
        help="Show received-frame metadata in the chat log.",
    )
    p_tui.set_defaults(func=_cmd_tui)

    return parser


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------
def _cmd_login(args: argparse.Namespace, console: Console) -> int:
    server = resolve_server(args.server)
    username = args.username
    if not username:
        try:
            username = input("Username: ").strip()
        except EOFError:
            console.print("[bold red]no username supplied[/]")
            return 1
    if not username:
        console.print("[bold red]username required[/]")
        return 1
    password = getpass.getpass("Password: ")
    if not password:
        console.print("[bold red]password required[/]")
        return 1

    client = ApiClient(server=server, token=None)
    payload = client.login(username=username, password=password)
    token = payload.get("token") if isinstance(payload, dict) else None
    if not token:
        console.print(f"[bold red]login response missing token:[/] {payload}")
        return 1

    creds = Credentials(server=server, token=token, username=username)
    path = save_credentials(creds)
    console.print(f"[green]logged in[/] as [bold]{username}[/] on {server}")
    console.print(f"[dim]credentials: {path}[/]")
    return 0


def _cmd_logout(_args: argparse.Namespace, console: Console) -> int:
    creds = load_credentials()
    if creds is None:
        console.print("[dim]not logged in[/]")
        return 0
    client = ApiClient(server=creds.server, token=creds.token)
    try:
        client.logout()
    except ApiError as exc:
        console.print(f"[yellow]server logout failed:[/] {exc}")
    cleared = clear_credentials()
    if cleared:
        console.print("[green]logged out[/]")
    else:
        console.print("[yellow]no credentials file to remove[/]")
    return 0


def _cmd_whoami(_args: argparse.Namespace, console: Console) -> int:
    creds = _require_credentials(console)
    if creds is None:
        return 1
    client = ApiClient(server=creds.server, token=creds.token)
    me = client.me()
    if not isinstance(me, dict):
        console.print(f"[bold red]unexpected /api/auth/me response:[/] {me}")
        return 1
    table = Table(show_header=False, box=None)
    table.add_row("server", creds.server)
    for key in ("username", "email", "is_staff", "is_superuser", "id"):
        if key in me:
            table.add_row(key, str(me[key]))
    console.print(table)
    return 0


def _cmd_doctor(args: argparse.Namespace, console: Console) -> int:
    server, token = _server_and_token(args.server)
    client = ApiClient(server=server, token=token)
    report = client.doctor()
    if not isinstance(report, dict):
        console.print(f"[bold red]unexpected /api/doctor/ response:[/] {report}")
        return 1
    overall = report.get("status", "unknown")
    checks = report.get("checks") or []
    table = Table(title="doctor", show_lines=False)
    table.add_column("check")
    table.add_column("status")
    table.add_column("detail", overflow="fold")
    for check in checks:
        if not isinstance(check, dict):
            continue
        status = str(check.get("status", "?"))
        style = _status_style(status)
        table.add_row(
            str(check.get("name", "?")),
            f"[{style}]{status}[/]",
            _format_detail(check.get("detail")),
        )
    console.print(table)
    console.print(f"overall: [{_status_style(overall)}]{overall}[/]")
    return 0 if overall in {"ok", "pass", "healthy"} else 2


def _cmd_status(args: argparse.Namespace, console: Console) -> int:
    server, token = _server_and_token(args.server)
    creds = load_credentials()
    table = Table(show_header=False, box=None)
    table.add_row("server", server)
    table.add_row("user", creds.username if creds else "[dim]not logged in[/]")
    table.add_row("token", "[green]present[/]" if token else "[dim]none[/]")

    client = ApiClient(server=server, token=token)
    try:
        client.health()
        table.add_row("server health", "[green]ok[/]")
    except ApiError as exc:
        table.add_row("server health", f"[red]{exc}[/]")
    console.print(table)
    return 0


def _cmd_chat(args: argparse.Namespace, console: Console) -> int:
    server, token, ok = _resolve_chat_auth(args, console)
    if not ok:
        return 1
    return run_chat_repl(
        server=server,
        token=token,
        as_id=args.as_id,
        session_id=args.session,
        console=console,
        debug=bool(getattr(args, "debug", False)),
    )


def _cmd_tui(args: argparse.Namespace, console: Console) -> int:
    server, token, ok = _resolve_chat_auth(args, console)
    if not ok:
        return 1
    return run_tui(
        server=server,
        token=token,
        as_id=args.as_id,
        session_id=args.session,
        debug=bool(getattr(args, "debug", False)),
    )


def _resolve_chat_auth(
    args: argparse.Namespace, console: Console
) -> tuple[str, str | None, bool]:
    """Common auth + server resolution for `chat` and `tui` subcommands."""
    server, token = _server_and_token(args.server)
    if args.no_auth:
        token = None
        if not args.as_id:
            console.print(
                "[yellow]warning:[/] --no-auth without --as <name> will likely be rejected"
            )
    elif token is None:
        console.print(
            "[bold red]not logged in.[/] Run [bold]surajclaw login[/] first, "
            "or use [bold]--no-auth --as <name>[/]."
        )
        return server, None, False
    return server, token, True


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _require_credentials(console: Console) -> Credentials | None:
    creds = load_credentials()
    if creds is None:
        console.print(
            "[bold red]not logged in.[/] Run [bold]surajclaw login[/] first."
        )
        console.print(f"[dim](expected at {credentials_path()})[/]")
        return None
    return creds


def _server_and_token(explicit_server: str | None) -> tuple[str, str | None]:
    """Resolve the active server URL and best-available token."""
    server = resolve_server(explicit_server)
    creds = load_credentials()
    if creds and creds.server == server:
        return server, creds.token
    return server, None


def _status_style(status: str) -> str:
    s = status.lower()
    if s in {"ok", "pass", "healthy", "ready"}:
        return "green"
    if s in {"warn", "warning", "degraded"}:
        return "yellow"
    return "red"


def _format_detail(detail: Any) -> str:
    if detail is None:
        return ""
    if isinstance(detail, str):
        return detail
    try:
        return json.dumps(detail, default=str)
    except (TypeError, ValueError):
        return str(detail)


if __name__ == "__main__":
    sys.exit(main())
