"""Google Workspace tool registration entry point.

Importing this module wires every Workspace tool (Gmail, Calendar, Tasks,
Drive, Docs, Sheets, Contacts, plus the accounts.list helper) into the
central tool registry. Listed in ``tools/registry.py::_ensure_builtin_tools_loaded``.
"""
from __future__ import annotations

from tools.google import (
    accounts,
    calendar,
    contacts,
    docs,
    drive,
    gmail,
    sheets,
    tasks,
)

accounts.register()
gmail.register()
calendar.register()
tasks.register()
drive.register()
docs.register()
sheets.register()
contacts.register()
