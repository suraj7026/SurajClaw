"""Shared types for SurajClaw's multi-agent graph runtime."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal


AgentStatus = Literal["ok", "needs_approval", "failed", "handoff", "retry"]
ToolRiskLevel = Literal["low", "medium", "high"]


@dataclass(frozen=True)
class AgentDefinition:
    """Registry entry for a directly invokable or delegatable agent graph."""

    id: str
    display_name: str
    description: str
    graph_factory: Callable[[], Any]
    system_prompt: str
    default_model_provider: str = "gemini"
    allowed_tools: frozenset[str] = field(default_factory=frozenset)
    direct_access: bool = True
    delegatable: bool = True
    max_steps: int = 6


@dataclass
class AgentInvocation:
    """Input envelope used by direct API/chat calls and orchestrator handoffs."""

    session_id: str
    source: str
    agent_id: str
    task: str
    account_label: str | None = None
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResult:
    """Normalized result returned from any specialized agent graph."""

    agent_id: str
    status: AgentStatus
    output: str
    structured: dict[str, Any] = field(default_factory=dict)
    next_agent: str | None = None
    approval_request_id: str | None = None


@dataclass(frozen=True)
class ToolDefinition:
    """Registry entry for an executable tool."""

    id: str
    callable: Callable[..., dict[str, Any]]
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)
    risk_level: ToolRiskLevel = "low"
    approval_required: bool = False
    required_env: tuple[str, ...] = ()


@dataclass
class ToolResult:
    """Normalized tool execution result."""

    ok: bool
    output: str
    structured: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    approved_by: str | None = None
    was_gated: bool = False
