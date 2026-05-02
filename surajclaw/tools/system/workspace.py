"""Safe workspace file tools."""
from __future__ import annotations

from pathlib import Path

from django.conf import settings

from agents.types import ToolDefinition
from tools.registry import register_tool


def _workspace_path(path: str) -> Path:
    root = Path(settings.WORKSPACE_DIR).resolve()
    target = (root / path).resolve()
    if root != target and root not in target.parents:
        raise ValueError("path escapes WORKSPACE_DIR")
    return target


def workspace_read_file(path: str, max_chars: int = 12000) -> dict:
    target = _workspace_path(path)
    if not target.is_file():
        return {"ok": False, "output": f"file not found: {path}", "error": "not_found"}
    text = target.read_text(encoding="utf-8", errors="replace")[:max_chars]
    return {"ok": True, "output": text, "structured": {"path": str(target)}}


def workspace_write_file(path: str, content: str) -> dict:
    target = _workspace_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return {"ok": True, "output": f"wrote {path}", "structured": {"path": str(target)}}


def workspace_list_files(path: str = ".", limit: int = 50) -> dict:
    target = _workspace_path(path)
    if not target.exists():
        return {"ok": False, "output": f"path not found: {path}", "error": "not_found"}
    if target.is_file():
        items = [target]
    else:
        items = sorted(target.iterdir(), key=lambda p: p.name)[: max(1, min(limit, 200))]
    lines = [str(item.relative_to(Path(settings.WORKSPACE_DIR).resolve())) for item in items]
    return {"ok": True, "output": "\n".join(lines) or "No files.", "structured": {"files": lines}}


register_tool(ToolDefinition("workspace.read_file", workspace_read_file, "Read a file under WORKSPACE_DIR."))
register_tool(ToolDefinition("workspace.write_file", workspace_write_file, "Write a file under WORKSPACE_DIR.", risk_level="medium"))
register_tool(ToolDefinition("workspace.list_files", workspace_list_files, "List files under WORKSPACE_DIR."))
