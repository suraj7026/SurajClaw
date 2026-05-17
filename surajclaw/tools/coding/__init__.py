"""Coding-agent tools.

Importing this package registers the headless coding spawner SurajClaw uses:

* ``coding.gemini_cli_run`` -- Google's headless ``gemini`` CLI, authenticated
  via your host ``~/.gemini`` OAuth directory (run ``gemini auth login`` first).

Antigravity is NOT registered here even though SurajClaw checks for it in
``manage.py codeassist_status``. Antigravity is a desktop IDE (a VS Code
fork) that exposes ``antigravity chat`` only against a running GUI window;
there is no headless / containerizable mode the coding agent can invoke.
"""
from tools.coding import gemini_cli  # noqa: F401

gemini_cli.register()
