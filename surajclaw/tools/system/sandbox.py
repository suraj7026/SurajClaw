"""Tools for sandboxed code execution."""
from __future__ import annotations

import shlex

from agents.types import ToolDefinition
from sandbox.docker_backend import get_sandbox_backend
from tools.registry import register_tool


def run_shell(command: str, timeout_seconds: int | None = None, session_id: str | None = None) -> dict:
    result = get_sandbox_backend().run_shell_command(command, timeout_seconds, session_id=session_id)
    return {
        "ok": result.ok,
        "output": result.stdout or result.stderr,
        "structured": {"stdout": result.stdout, "stderr": result.stderr, "code": result.code},
        "error": None if result.ok else "nonzero_exit",
    }


def run_python(command: str, timeout_seconds: int | None = None, session_id: str | None = None) -> dict:
    script = command
    if "python" not in command[:20].lower():
        script = "python3 - <<'PY'\n" + command + "\nPY"
    return run_shell(script, timeout_seconds, session_id=session_id)


def read_file(path: str, session_id: str | None = None) -> dict:
    quoted = shlex.quote(path)
    return run_shell(f"test -f {quoted} && sed -n '1,200p' {quoted}", session_id=session_id)


def write_file(path: str, content: str, session_id: str | None = None) -> dict:
    quoted = shlex.quote(path)
    safe_content = shlex.quote(content)
    return run_shell(f"printf %s {safe_content} > {quoted}", session_id=session_id)


def run_tests(command: str = "pytest", timeout_seconds: int | None = None, session_id: str | None = None) -> dict:
    return run_shell(command, timeout_seconds, session_id=session_id)


register_tool(ToolDefinition("sandbox.run_shell", run_shell, "Run a shell command in Docker sandbox.", risk_level="medium"))
register_tool(ToolDefinition("sandbox.run_python", run_python, "Run Python in Docker sandbox.", risk_level="medium"))
register_tool(ToolDefinition("sandbox.read_file", read_file, "Read a file in Docker sandbox."))
register_tool(ToolDefinition("sandbox.write_file", write_file, "Write a file in Docker sandbox.", risk_level="medium"))
register_tool(ToolDefinition("sandbox.run_tests", run_tests, "Run tests in Docker sandbox.", risk_level="medium"))
