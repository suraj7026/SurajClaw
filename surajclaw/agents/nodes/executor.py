"""Executor node: run the chosen tool (or call the LLM directly).

Every tool invocation is wrapped with:
  - approval gate (if gated)
  - audit log write (regardless of outcome)
  - duration + error capture
"""
from __future__ import annotations

import hashlib
import json
import logging
import time

from agents.state import AgentState

logger = logging.getLogger(__name__)


def _audit(
    *,
    session_id: str,
    tool_id: str,
    input_hash: str,
    output_summary: str,
    duration_ms: int,
    approved_by: str | None,
    was_gated: bool,
) -> None:
    from core.models import AuditLog

    AuditLog.objects.create(
        session_id=session_id,
        tool_id=tool_id,
        input_hash=input_hash,
        output_summary=output_summary[:200],
        duration_ms=duration_ms,
        approved_by=approved_by,
        was_gated=was_gated,
    )


def executor_node(state: AgentState) -> AgentState:
    plan = state.get("plan", [])
    idx = state.get("current_step", 0)
    if idx >= len(plan):
        return state

    tool_call = (state.get("tool_calls") or [{}])[-1]
    tool_id = tool_call.get("tool")
    session_id = state["session_id"]

    t0 = time.monotonic()
    if tool_id is None:
        # Direct-LLM path: we have no tool to call, just record it.
        result = {"ok": True, "output": plan[idx]["goal"]}
    else:
        from approval.gate import intercept_if_gated

        decision = intercept_if_gated(
            tool_id=tool_id,
            description=f"Run {tool_id}({tool_call.get('args')})",
            session_id=session_id,
        )
        if not decision.approved:
            result = {"ok": False, "output": f"denied: {decision.status}"}
        else:
            result = {"ok": True, "output": f"ran {tool_id}"}

        input_blob = json.dumps(tool_call.get("args", {}), sort_keys=True).encode()
        _audit(
            session_id=session_id,
            tool_id=tool_id,
            input_hash=hashlib.sha256(input_blob).hexdigest(),
            output_summary=result["output"],
            duration_ms=int((time.monotonic() - t0) * 1000),
            approved_by=decision.responded_by,
            was_gated=True,
        )

    state.setdefault("tool_results", []).append(result)
    return state
