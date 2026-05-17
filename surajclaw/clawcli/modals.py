"""Textual modal screens for the SurajClaw TUI.

* ModelPickerModal     — select a Gemini model (sends !model directive)
* SessionPickerModal   — browse and resume recent sessions via /api/sessions/
* ApprovalModal        — approve or reject a gated tool call
* GoogleAccountsModal  — list / connect / disconnect Google Workspace accounts
"""
from __future__ import annotations

import asyncio
import webbrowser
from typing import Any

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, ListItem, ListView, Static

_GEMINI_MODELS: list[tuple[str, str]] = [
    # Gemini 3.x family
    ("gemini-3.1-flash-lite", "default · loosest RPM · 3.x lite"),
    ("gemini-3-flash", "balanced · 3.x flash"),
    ("gemini-3.1-pro-preview", "deepest reasoning · 3.1 pro · preview"),
    ("gemini-3.1-flash-live-preview", "low-latency · live variant · preview"),
    # Gemini 2.x family (kept for fallback / known stable RPM)
    ("gemini-2.5-flash-lite", "2.5 lite · loose RPM"),
    ("gemini-2.5-flash", "2.5 flash · balanced"),
    ("gemini-2.5-pro", "2.5 pro · low RPM"),
    ("gemini-2.0-flash", "2.0 flash · previous generation"),
    ("gemini-2.0-flash-thinking-exp", "2.0 · experimental thinking mode"),
]


class ModelPickerModal(ModalScreen[str | None]):
    """Overlay to pick a Gemini model. Dismissed with the model string, or None."""

    DEFAULT_CSS = """
    ModelPickerModal { align: center middle; }
    ModelPickerModal > Vertical {
        width: 64; height: auto; max-height: 20;
        border: round $accent; background: $surface; padding: 1 2;
    }
    ModelPickerModal #title { text-style: bold; padding-bottom: 1; }
    ModelPickerModal ListView { height: auto; max-height: 10; border: round $accent-darken-2; }
    ModelPickerModal Button { margin-top: 1; }
    """

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("Select model  (↑↓ navigate, Enter select, Esc cancel)", id="title")
            yield ListView(
                *[
                    ListItem(Static(Text(m, style="bold") + Text(f"  {desc}", style="dim")))
                    for m, desc in _GEMINI_MODELS
                ],
                id="model-list",
            )
            yield Button("Cancel", variant="default", id="cancel")

    def on_mount(self) -> None:
        self.query_one("#model-list", ListView).focus()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        items = list(self.query(ListItem))
        try:
            idx = items.index(event.item)
        except ValueError:
            self.dismiss(None)
            return
        self.dismiss(_GEMINI_MODELS[idx][0] if idx < len(_GEMINI_MODELS) else None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(None)

    def on_key(self, event: Any) -> None:
        if event.key == "escape":
            self.dismiss(None)


class SessionPickerModal(ModalScreen[str | None]):
    """Overlay showing recent sessions fetched from /api/sessions/."""

    DEFAULT_CSS = """
    SessionPickerModal { align: center middle; }
    SessionPickerModal > Vertical {
        width: 72; height: auto; max-height: 24;
        border: round $accent; background: $surface; padding: 1 2;
    }
    SessionPickerModal #title { text-style: bold; padding-bottom: 1; }
    SessionPickerModal ListView { height: auto; max-height: 16; border: round $accent-darken-2; }
    SessionPickerModal #info { color: $text-muted; padding: 0 0 1 0; }
    SessionPickerModal Button { margin-top: 1; }
    """

    def __init__(self, *, server: str, token: str | None) -> None:
        super().__init__()
        self._server = server
        self._token = token
        self._sessions: list[dict[str, Any]] = []

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("Recent sessions  (↑↓ navigate, Enter resume, Esc cancel)", id="title")
            yield Static("loading...", id="info")
            yield ListView(id="session-list")
            yield Button("Cancel", variant="default", id="cancel")

    async def on_mount(self) -> None:
        self.query_one("#session-list", ListView).focus()
        asyncio.create_task(self._load_sessions())

    async def _load_sessions(self) -> None:
        from clawcli.http import ApiClient, ApiError

        info = self.query_one("#info", Static)
        lv = self.query_one("#session-list", ListView)

        loop = asyncio.get_event_loop()
        try:
            client = ApiClient(server=self._server, token=self._token)
            data = await loop.run_in_executor(
                None,
                lambda: client.get("/api/sessions/", ordering="-started_at", page_size=30),
            )
        except ApiError as exc:
            info.update(Text(f"Could not load sessions: {exc}", style="bold red"))
            return
        except Exception as exc:  # noqa: BLE001
            info.update(Text(f"Error: {exc}", style="bold red"))
            return

        sessions = data if isinstance(data, list) else data.get("results", [])
        self._sessions = sessions

        if not sessions:
            info.update(Text("No sessions found.", style="dim"))
            return

        info.update(Text(f"{len(sessions)} sessions", style="dim"))
        for s in sessions:
            sid = str(s.get("id", ""))
            source = s.get("source", "")
            started = str(s.get("started_at", ""))[:16].replace("T", " ")
            summary = s.get("summary") or ""
            count = s.get("message_count", "?")
            label = (
                Text(sid[:8], style="bold")
                + Text(f"…  {source}  {started}  [{count} msgs]", style="dim")
                + (Text(f"  {summary[:40]}", style="italic dim") if summary else Text(""))
            )
            await lv.append(ListItem(Static(label)))

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        items = list(self.query(ListItem))
        try:
            idx = items.index(event.item)
        except ValueError:
            self.dismiss(None)
            return
        self.dismiss(
            str(self._sessions[idx].get("id", "")) if idx < len(self._sessions) else None
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(None)

    def on_key(self, event: Any) -> None:
        if event.key == "escape":
            self.dismiss(None)


class ApprovalModal(ModalScreen[str | None]):
    """Overlay to approve or deny a gated tool call.

    Dismissed with ``"approved"`` or ``"rejected"``.
    """

    DEFAULT_CSS = """
    ApprovalModal { align: center middle; }
    ApprovalModal > Vertical {
        width: 66; height: auto;
        border: round $warning; background: $surface; padding: 1 2;
    }
    ApprovalModal #title { text-style: bold; color: $warning; padding-bottom: 1; }
    ApprovalModal #description { padding-bottom: 1; color: $text; }
    ApprovalModal #hint { color: $text-muted; padding-bottom: 1; }
    ApprovalModal Button { margin-right: 1; }
    """

    def __init__(self, *, request_id: str, description: str) -> None:
        super().__init__()
        self._request_id = request_id
        self._description = description

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("⚠  Approval required", id="title")
            yield Static(self._description, id="description")
            yield Static("a = approve · r = reject · Esc = reject", id="hint")
            yield Button("Approve  [a]", variant="success", id="approve")
            yield Button("Reject   [r]", variant="error", id="reject")

    def on_mount(self) -> None:
        self.query_one("#approve", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss("approved" if event.button.id == "approve" else "rejected")

    def on_key(self, event: Any) -> None:
        if event.key == "escape" or event.key == "r":
            self.dismiss("rejected")
        elif event.key == "a":
            self.dismiss("approved")


class GoogleAccountsModal(ModalScreen[bool]):
    """List, connect, and disconnect Google Workspace OAuth accounts.

    Connecting opens the system browser at the auth URL returned by
    ``POST /api/google/accounts/<label>/connect/``. The browser-side
    callback (``/api/google/accounts/callback/``) writes the token file
    server-side, so the user just hits "Refresh" here once they finish.
    """

    DEFAULT_CSS = """
    GoogleAccountsModal { align: center middle; }
    GoogleAccountsModal > Vertical {
        width: 78; height: auto; max-height: 28;
        border: round $accent; background: $surface; padding: 1 2;
    }
    GoogleAccountsModal #title { text-style: bold; padding-bottom: 1; }
    GoogleAccountsModal #info { color: $text-muted; padding-bottom: 1; }
    GoogleAccountsModal ListView { height: auto; max-height: 10; border: round $accent-darken-2; }
    GoogleAccountsModal #label-input { margin-top: 1; }
    GoogleAccountsModal #buttons { height: auto; layout: horizontal; margin-top: 1; }
    GoogleAccountsModal Button { margin-right: 1; }
    """

    def __init__(self, *, server: str, token: str | None) -> None:
        super().__init__()
        self._server = server
        self._token = token
        self._accounts: list[dict[str, Any]] = []

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("Google Workspace accounts", id="title")
            yield Static("(Enter a label below and click Add to start OAuth in your browser)", id="info")
            yield ListView(id="account-list")
            yield Input(placeholder="new account label (e.g. work, personal2)", id="label-input")
            with Horizontal(id="buttons"):
                yield Button("Add", variant="success", id="add")
                yield Button("Refresh", variant="default", id="refresh")
                yield Button("Remove selected", variant="error", id="remove")
                yield Button("Close", variant="default", id="close")

    async def on_mount(self) -> None:
        asyncio.create_task(self._load_accounts())

    async def _load_accounts(self) -> None:
        from clawcli.http import ApiClient, ApiError

        info = self.query_one("#info", Static)
        lv = self.query_one("#account-list", ListView)
        await lv.clear()
        info.update(Text("loading...", style="dim"))

        loop = asyncio.get_event_loop()
        try:
            client = ApiClient(server=self._server, token=self._token)
            data = await loop.run_in_executor(
                None, lambda: client.get("/api/google/accounts/")
            )
        except ApiError as exc:
            info.update(Text(f"Could not load accounts: {exc}", style="bold red"))
            return
        except Exception as exc:  # noqa: BLE001
            info.update(Text(f"Error: {exc}", style="bold red"))
            return

        accounts = data if isinstance(data, list) else data.get("results") or data.get("accounts") or []
        self._accounts = accounts
        if not accounts:
            info.update(Text("no accounts connected yet — add one below.", style="dim"))
            return
        info.update(Text(f"{len(accounts)} account(s) connected. Select one to remove.", style="dim"))
        for a in accounts:
            label = a.get("label") or a.get("name") or "?"
            email = a.get("email") or ""
            status = a.get("status") or ("ok" if a.get("connected", True) else "expired")
            row = (
                Text(label, style="bold")
                + Text(f"  {email}", style="dim")
                + Text(f"  [{status}]", style="green" if status == "ok" else "yellow")
            )
            await lv.append(ListItem(Static(row)))

    async def _start_connect(self, label: str) -> None:
        from clawcli.http import ApiClient, ApiError

        info = self.query_one("#info", Static)
        loop = asyncio.get_event_loop()
        try:
            client = ApiClient(server=self._server, token=self._token)
            data = await loop.run_in_executor(
                None,
                lambda: client.post(f"/api/google/accounts/{label}/connect/"),
            )
        except ApiError as exc:
            info.update(Text(f"connect failed: {exc}", style="bold red"))
            return
        except Exception as exc:  # noqa: BLE001
            info.update(Text(f"connect error: {exc}", style="bold red"))
            return

        auth_url = (data or {}).get("auth_url")
        if not auth_url:
            info.update(Text("server did not return an auth_url", style="bold red"))
            return
        try:
            webbrowser.open(auth_url)
        except Exception:  # noqa: BLE001
            pass
        info.update(
            Text(
                f"opened browser for `{label}` — finish Google consent there, then press Refresh.",
                style="bold green",
            )
        )

    async def _remove_selected(self) -> None:
        from clawcli.http import ApiClient, ApiError

        info = self.query_one("#info", Static)
        lv = self.query_one("#account-list", ListView)
        idx = lv.index
        if idx is None or idx < 0 or idx >= len(self._accounts):
            info.update(Text("select an account first.", style="bold yellow"))
            return
        label = self._accounts[idx].get("label") or self._accounts[idx].get("name") or ""
        if not label:
            return
        loop = asyncio.get_event_loop()
        try:
            client = ApiClient(server=self._server, token=self._token)
            await loop.run_in_executor(
                None,
                lambda: client._request("DELETE", f"/api/google/accounts/{label}/"),
            )
        except ApiError as exc:
            info.update(Text(f"remove failed: {exc}", style="bold red"))
            return
        except Exception as exc:  # noqa: BLE001
            info.update(Text(f"remove error: {exc}", style="bold red"))
            return
        info.update(Text(f"removed `{label}`.", style="bold green"))
        await self._load_accounts()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "add":
            label = self.query_one("#label-input", Input).value.strip()
            if not label:
                self.query_one("#info", Static).update(
                    Text("enter a label first.", style="bold yellow")
                )
                return
            self.query_one("#label-input", Input).value = ""
            await self._start_connect(label)
        elif bid == "refresh":
            await self._load_accounts()
        elif bid == "remove":
            await self._remove_selected()
        elif bid == "close":
            self.dismiss(True)

    def on_key(self, event: Any) -> None:
        if event.key == "escape":
            self.dismiss(True)
