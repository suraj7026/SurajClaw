"""Central tool registry with access checks, approvals, and audit logging."""
from __future__ import annotations

import hashlib
import inspect
import json
import os
import re
import time
from typing import Any, get_type_hints

from agents.types import ToolDefinition, ToolResult


_TOOLS: dict[str, ToolDefinition] = {}
_BUILTINS_LOADED = False


def register_tool(tool: ToolDefinition) -> ToolDefinition:
    """Register a tool definition. Safe to call repeatedly at import time."""
    _TOOLS[tool.id] = tool
    return tool


def get_tool(tool_id: str) -> ToolDefinition:
    try:
        return _TOOLS[tool_id]
    except KeyError as exc:
        raise LookupError(f"unknown tool: {tool_id}") from exc


def list_tools() -> list[ToolDefinition]:
    _ensure_builtin_tools_loaded()
    return sorted(_TOOLS.values(), key=lambda t: t.id)


def list_tools_for_agent(agent_id: str) -> list[ToolDefinition]:
    from agents.registry import get_agent

    _ensure_builtin_tools_loaded()
    agent = get_agent(agent_id)
    return [tool for tool in list_tools() if tool.id in agent.allowed_tools]


def execute_tool(
    *,
    agent_id: str,
    tool_id: str,
    args: dict[str, Any],
    session_id: str,
) -> ToolResult:
    """Execute a registered tool after access, env, approval, and audit checks."""
    from agents.registry import get_agent
    from approval.gate import intercept_if_gated

    _ensure_builtin_tools_loaded()
    agent = get_agent(agent_id)
    if tool_id not in agent.allowed_tools:
        return ToolResult(
            ok=False,
            output=f"agent `{agent_id}` cannot use tool `{tool_id}`",
            error="tool_not_allowed",
        )

    try:
        tool = get_tool(tool_id)
    except LookupError as exc:
        return ToolResult(ok=False, output=str(exc), error="unknown_tool")

    missing = [name for name in tool.required_env if not os.environ.get(name)]
    if missing:
        return ToolResult(
            ok=False,
            output=f"missing required environment variable(s): {', '.join(missing)}",
            error="missing_env",
        )

    approval = intercept_if_gated(
        tool_id=tool_id,
        description=f"{agent_id} wants to run {tool_id} with {args}",
        session_id=session_id,
        timeout_seconds=600,
    )
    if not approval.approved:
        result = ToolResult(
            ok=False,
            output=f"denied: {approval.status}",
            error="approval_denied",
            approved_by=approval.responded_by,
            was_gated=True,
        )
        _audit(session_id, agent_id, tool_id, args, result, 0)
        return result

    t0 = time.monotonic()
    call_args = dict(args)
    if "session_id" in inspect.signature(tool.callable).parameters:
        call_args.setdefault("session_id", session_id)

    try:
        raw = tool.callable(**call_args)
        result = ToolResult(
            ok=bool(raw.get("ok", True)),
            output=str(raw.get("output", "")),
            structured=raw.get("structured", {}) or {},
            error=raw.get("error"),
            approved_by=approval.responded_by,
            was_gated=tool.approval_required,
        )
    except Exception as exc:  # noqa: BLE001 -- tool failures return to graph
        result = ToolResult(ok=False, output=f"tool failed: {exc}", error=type(exc).__name__)

    duration_ms = int((time.monotonic() - t0) * 1000)
    _audit(session_id, agent_id, tool_id, args, result, duration_ms)
    return result


def get_langchain_tools(agent_id: str, session_id: str | None = None):
    """Return LangChain StructuredTools for tools allowed to ``agent_id``."""
    from langchain_core.tools import StructuredTool
    from pydantic import Field, create_model

    tools = []
    for tool in list_tools_for_agent(agent_id):
        fields: dict[str, tuple[Any, Any]] = {}
        type_hints = get_type_hints(tool.callable)
        for name, param in inspect.signature(tool.callable).parameters.items():
            if name == "session_id":
                continue
            annotation = type_hints.get(name, Any)
            default = param.default if param.default is not inspect._empty else ...
            fields[name] = (annotation, Field(default=default))
        args_schema = create_model(f"{_safe_tool_name(tool.id)}Args", **fields)

        def _runner(_tool_id=tool.id, **kwargs):
            result = execute_tool(
                agent_id=agent_id,
                tool_id=_tool_id,
                args=kwargs,
                session_id=session_id or "",
            )
            if result.ok:
                return result.output
            return f"ERROR ({result.error or 'tool_failed'}): {result.output}"

        tools.append(
            StructuredTool.from_function(
                func=_runner,
                name=_safe_tool_name(tool.id),
                description=f"{tool.description}\nOriginal tool id: {tool.id}",
                args_schema=args_schema,
            )
        )
    return tools


def _safe_tool_name(tool_id: str) -> str:
    name = re.sub(r"[^a-zA-Z0-9_]", "_", tool_id)
    if not name or name[0].isdigit():
        name = f"tool_{name}"
    return name[:64]


def _audit(
    session_id: str,
    agent_id: str,
    tool_id: str,
    args: dict[str, Any],
    result: ToolResult,
    duration_ms: int,
) -> None:
    try:
        from core.models import AuditLog, Session

        session = Session.objects.filter(id=session_id).first()
        input_blob = json.dumps(args, sort_keys=True, default=str).encode()
        AuditLog.objects.create(
            session=session,
            tool_id=f"{agent_id}:{tool_id}"[:128],
            input_hash=hashlib.sha256(input_blob).hexdigest(),
            output_summary=(result.output or result.error or "")[:200],
            duration_ms=duration_ms,
            approved_by=result.approved_by,
            was_gated=result.was_gated,
        )
    except Exception:
        # Audit should never crash the graph; deployment may be mid-migration.
        return


def _ensure_builtin_tools_loaded() -> None:
    global _BUILTINS_LOADED
    if _BUILTINS_LOADED:
        return
    import tools.google.workspace  # noqa: F401
    import tools.memory  # noqa: F401
    import tools.notes  # noqa: F401
    import tools.system.sandbox  # noqa: F401
    import tools.system.workspace  # noqa: F401
    import tools.web  # noqa: F401

    _BUILTINS_LOADED = True
