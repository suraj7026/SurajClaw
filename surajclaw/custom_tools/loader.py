"""Hot-load validated CustomTool definitions into the LangGraph registry.

Source code stored in a CustomTool row is a Python function body (not a
full module). The loader wraps it with a LangChain `@tool` decorator and
exposes it in the tool registry so the agent can call it by name.

Security: execution of user-provided source in-process is dangerous. We
guard with:
  1. `is_validated=True` gate (someone ran the sandbox test suite against it)
  2. `is_active=True` toggle (admin can disable instantly)
  3. AST allowlist (no imports beyond an approved list; no `open`, `eval`, etc.)
The validation step itself is out-of-scope for the loader.
"""
from __future__ import annotations

import ast
import logging
from typing import Callable

logger = logging.getLogger(__name__)

_ALLOWED_IMPORT_ROOTS = {"httpx", "json", "re", "datetime", "math"}


def _ast_is_safe(source: str) -> tuple[bool, str]:
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return False, f"syntax error: {exc}"
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                if root not in _ALLOWED_IMPORT_ROOTS:
                    return False, f"disallowed import: {alias.name}"
        if isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".", 1)[0]
            if root not in _ALLOWED_IMPORT_ROOTS:
                return False, f"disallowed import-from: {node.module}"
        if isinstance(node, ast.Name) and node.id in {"eval", "exec", "open", "__import__"}:
            return False, f"disallowed name: {node.id}"
    return True, ""


def load_custom_tools() -> list[Callable]:
    from custom_tools.models import CustomTool

    loaded: list[Callable] = []
    for row in CustomTool.objects.filter(is_active=True, is_validated=True):
        ok, why = _ast_is_safe(row.source_code)
        if not ok:
            logger.warning("skip custom tool %s: %s", row.name, why)
            continue
        namespace: dict = {}
        try:
            exec(compile(row.source_code, f"<custom_tool:{row.name}>", "exec"), namespace)  # noqa: S102
        except (SyntaxError, NameError, ValueError) as exc:
            logger.warning("custom tool %s failed to load: %s", row.name, exc)
            continue
        fn = namespace.get(row.name)
        if not callable(fn):
            logger.warning("custom tool %s: source did not define %s()", row.name, row.name)
            continue
        fn.__doc__ = fn.__doc__ or row.description
        loaded.append(fn)
    return loaded
