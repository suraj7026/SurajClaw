"""``agents.spawn_subagent`` -- the General Agent's escape hatch.

Lets the orchestrator spin up an ephemeral, session-scoped subagent for a
focused multi-step task that doesn't fit one of the built-in specialists.
The subagent reuses the existing ``register_custom_agent`` +
``build_custom_graph`` plumbing, so it goes through the same access-check
/ approval-gate / audit-log pipeline as everything else.

Safety boundary: ``SPAWNABLE_TOOLS`` is the user-facing allowlist of tool
ids the General Agent is permitted to grant to a spawned subagent. The
General Agent CANNOT widen this -- requests for tools outside this set
fail before the subagent is registered. Destructive Google/Browser/
Coding tools are excluded by design.

Approval: spawning a subagent with no tools is free; spawning one with
any tool requires explicit operator approval (see ``approval/gate.py``
dynamic gate hook).
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from agents.types import AgentInvocation, ToolDefinition
from tools.registry import register_tool

logger = logging.getLogger(__name__)


SPAWNABLE_TOOLS: frozenset[str] = frozenset(
    {
        "web.search",
        "memory.search",
        "workspace.read_file",
        "workspace.write_file",
        "workspace.list_files",
        "sandbox.run_shell",
        "sandbox.run_python",
        "sandbox.read_file",
        "sandbox.write_file",
        "sandbox.run_tests",
        "notes.write",
        "notes.search",
        "notes.list",
    }
)


def spawn_subagent(
    name: str,
    system_prompt: str,
    task: str,
    allowed_tools: list[str] | None = None,
    max_steps: int = 4,
    session_id: str = "",
) -> dict[str, Any]:
    """Register a one-shot subagent and run it inline.

    Args:
        name: short descriptive label (becomes part of the agent id).
        system_prompt: focused instruction for the throwaway agent.
        task: the request the subagent should solve.
        allowed_tools: tool ids; must be a subset of ``SPAWNABLE_TOOLS``.
        max_steps: loop cap (default 4, hard-capped at 6).
        session_id: injected by the registry; used for streaming + memory.
    """
    if not name or not system_prompt or not task:
        return {
            "ok": False,
            "output": "name, system_prompt, and task are all required",
            "error": "missing_args",
        }

    requested = set(allowed_tools or [])
    extra = requested - SPAWNABLE_TOOLS
    if extra:
        return {
            "ok": False,
            "output": (
                "subagent requested tools outside the spawnable allowlist: "
                + ", ".join(sorted(extra))
                + ". Allowed: "
                + ", ".join(sorted(SPAWNABLE_TOOLS))
            ),
            "error": "tools_not_spawnable",
        }

    from agents.invocation import invoke_agent
    from agents.registry import register_custom_agent

    agent_id = f"spawn_{(session_id or 'anon')[:8]}_{uuid.uuid4().hex[:8]}"
    safe_name = "".join(c if c.isalnum() else "_" for c in name)[:40] or "subagent"
    try:
        register_custom_agent(
            agent_id=agent_id,
            display_name=f"Spawn: {safe_name}",
            system_prompt=system_prompt,
            allowed_tools=requested,
            max_steps=max(1, min(max_steps, 6)),
        )
    except ValueError as exc:
        return {"ok": False, "output": str(exc), "error": "registration_failed"}

    invocation = AgentInvocation(
        session_id=session_id or "",
        source="spawn",
        agent_id=agent_id,
        task=task,
    )
    result = invoke_agent(invocation)
    return {
        "ok": result.status == "ok",
        "output": result.output,
        "structured": {
            "agent_id": agent_id,
            "name": safe_name,
            "allowed_tools": sorted(requested),
            "status": result.status,
            "tool_call_log": result.structured.get("tool_call_log", [])
            if isinstance(result.structured, dict)
            else [],
        },
        "error": None if result.status == "ok" else result.status,
    }


def needs_approval(args: dict[str, Any]) -> bool:
    """Dynamic-gate hook: only gate when ``allowed_tools`` is non-empty.

    A toolless subagent can only read messages and answer in plain text,
    so it's free. Anything with tool access needs operator OK.
    """
    requested = args.get("allowed_tools") or []
    if isinstance(requested, str):
        return bool(requested.strip())
    return bool(list(requested))


def register() -> None:
    register_tool(
        ToolDefinition(
            id="agents.spawn_subagent",
            callable=spawn_subagent,
            description=(
                "Spawn a focused, ephemeral subagent for a multi-step generic "
                "task that doesn't fit GOOGLE_WORKSPACE, BROWSER, CODE, "
                "CODE_EXECUTOR, or NOTES. Args: name (short label), "
                "system_prompt (instruction for the subagent), task (the "
                "request), allowed_tools (subset of: "
                + ", ".join(sorted(SPAWNABLE_TOOLS))
                + "), max_steps (default 4, cap 6). Spawning with tools is "
                "gated for operator approval."
            ),
            risk_level="medium",
        )
    )
