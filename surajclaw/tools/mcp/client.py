"""MCP (Model Context Protocol) client.

Spawns each server defined in ``settings.MCP_SERVERS``, discovers the tools
it offers, and registers them in the central tool registry. Tool ids are
namespaced as ``mcp.<server>.<tool>`` so the existing access-check /
approval-gate / audit pipeline in ``tools.registry.execute_tool`` applies
uniformly to local and MCP-backed tools.

Concurrency model: MCP uses asyncio. We run a dedicated event loop in a
daemon thread and submit coroutines onto it via ``asyncio.run_coroutine_threadsafe``.
Each tool's ``callable`` is a sync shim that blocks until the future
completes. This keeps the rest of the codebase free of async churn.

Failure mode: discovery is best-effort. If a server doesn't start or
``langchain-mcp-adapters`` isn't installed, we log a warning and skip --
the agent still functions with whatever in-proc tools are available.
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
from concurrent.futures import Future
from typing import Any

from django.conf import settings

from agents.types import ToolDefinition
from tools.registry import register_tool

logger = logging.getLogger(__name__)


_REGISTERED = False
_LOOP: asyncio.AbstractEventLoop | None = None
_LOOP_THREAD: threading.Thread | None = None
_CLIENT: Any = None
_TOOLS_BY_QUALIFIED_ID: dict[str, Any] = {}


def _start_background_loop() -> asyncio.AbstractEventLoop:
    """Spin up a dedicated event loop in a daemon thread (idempotent)."""
    global _LOOP, _LOOP_THREAD
    if _LOOP is not None and _LOOP.is_running():
        return _LOOP

    loop = asyncio.new_event_loop()

    def _run():
        asyncio.set_event_loop(loop)
        loop.run_forever()

    thread = threading.Thread(target=_run, name="mcp-loop", daemon=True)
    thread.start()
    _LOOP = loop
    _LOOP_THREAD = thread
    return loop


def _run_coro_blocking(coro, timeout: int) -> Any:
    loop = _start_background_loop()
    future: Future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result(timeout=timeout)


def _build_client(servers: list[dict[str, Any]]):
    """Translate the SurajClaw MCP server spec into the adapter's shape."""
    from langchain_mcp_adapters.client import MultiServerMCPClient

    spec: dict[str, dict[str, Any]] = {}
    for s in servers:
        name = s.get("name")
        if not name:
            logger.warning("MCP server entry missing 'name'; skipping: %s", s)
            continue
        spec[name] = {k: v for k, v in s.items() if k != "name"}
        spec[name].setdefault("transport", "stdio")
    return MultiServerMCPClient(spec)


def register_mcp_tools() -> None:
    """Discover tools from every configured server and register them.

    Idempotent: safe to call multiple times; subsequent calls are no-ops.
    """
    global _REGISTERED, _CLIENT
    if _REGISTERED:
        return
    servers = getattr(settings, "MCP_SERVERS", None) or []
    if not servers:
        _REGISTERED = True
        return

    try:
        client = _build_client(servers)
    except ImportError as exc:
        logger.warning(
            "MCP servers configured but langchain-mcp-adapters not installed: %s", exc
        )
        _REGISTERED = True
        return
    except Exception as exc:  # noqa: BLE001
        logger.exception("failed to build MCP client: %s", exc)
        _REGISTERED = True
        return

    timeout = int(getattr(settings, "MCP_DISCOVERY_TIMEOUT", 20))
    try:
        lc_tools = _run_coro_blocking(client.get_tools(), timeout=timeout)
    except Exception as exc:  # noqa: BLE001
        logger.exception("MCP tool discovery failed: %s", exc)
        _REGISTERED = True
        return

    _CLIENT = client
    server_names = {s["name"] for s in servers if "name" in s}
    for lc_tool in lc_tools:
        server_name = _infer_server_name(lc_tool, server_names)
        tool_name = getattr(lc_tool, "name", None) or "unknown"
        qualified = f"mcp.{server_name}.{tool_name}"
        _TOOLS_BY_QUALIFIED_ID[qualified] = lc_tool

        register_tool(
            ToolDefinition(
                id=qualified,
                callable=_make_callable(qualified, lc_tool),
                description=(getattr(lc_tool, "description", "") or tool_name),
            )
        )
        logger.info("registered MCP tool %s", qualified)

    _REGISTERED = True


def _infer_server_name(lc_tool: Any, known: set[str]) -> str:
    """Best-effort: pull the server name off the tool's metadata."""
    meta = getattr(lc_tool, "metadata", None) or {}
    for key in ("server_name", "server", "mcp_server"):
        val = meta.get(key) if isinstance(meta, dict) else None
        if val and val in known:
            return val
    if len(known) == 1:
        return next(iter(known))
    return "unknown"


def _make_callable(qualified_id: str, lc_tool: Any):
    """Return a sync callable that invokes the underlying LangChain tool.

    The callable accepts arbitrary keyword args; LangChain validates them
    against the tool's args_schema. Result must be a dict per the
    ``ToolDefinition.callable`` contract.
    """
    def _call(**kwargs):  # noqa: ANN003
        try:
            # langchain-mcp-adapters returns sync StructuredTool wrappers that
            # internally handle async dispatch. .invoke() is the safe entry.
            raw = lc_tool.invoke(kwargs)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "output": f"mcp tool {qualified_id} failed: {exc}", "error": type(exc).__name__}

        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str):
            return {"ok": True, "output": raw, "structured": {}}
        # Some MCP tools return a list of content parts.
        try:
            output_str = json.dumps(raw, default=str)
        except Exception:
            output_str = str(raw)
        return {"ok": True, "output": output_str, "structured": {"raw": raw} if not isinstance(raw, (list, tuple)) else {"items": list(raw)}}

    _call.__name__ = qualified_id.replace(".", "_")
    return _call


def list_mcp_tool_ids() -> list[str]:
    return sorted(_TOOLS_BY_QUALIFIED_ID.keys())
