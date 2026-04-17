"""Slash command registry + detection.

Adapted from OpenClaw's ``src/auto-reply/command-detection.ts`` and
``commands-registry.ts``. We support ``/`` and ``!`` as command prefixes,
text aliases per command, and a small set of "abort" triggers that always
short-circuit a running turn.

The agent pipeline calls :func:`detect` *before* enqueuing a Celery turn.
If a command matches, we run its handler synchronously and skip the LLM
entirely — these are control-plane operations (status, stop, list notes),
not chat.
"""
from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# OpenClaw uses both `/` and `!` as command leaders — we keep parity so users
# coming from there are not surprised. Bash-friendly `!` is handy on Telegram.
PREFIXES = ("/", "!")

# Triggers that abort whatever the agent is currently doing for the session.
ABORT_TRIGGERS = frozenset({"stop", "abort", "cancel", "halt", "kill"})


@dataclass(frozen=True)
class CommandMatch:
    name: str
    args: str
    raw: str


CommandHandler = Callable[["CommandContext"], "CommandResult"]


@dataclass
class CommandContext:
    """Everything a command handler is allowed to see.

    Kept narrow on purpose — handlers should not pull in the full Django
    request or LangGraph state. If a handler needs more, add a typed field
    here and pass it from the dispatcher.
    """

    session_id: str
    sender_id: str | None
    channel: str  # "web" | "telegram" | ...
    args: str
    is_owner: bool


@dataclass
class CommandResult:
    text: str
    handled: bool = True
    abort_turn: bool = False


@dataclass(frozen=True)
class Command:
    name: str
    aliases: tuple[str, ...]
    description: str
    accepts_args: bool
    owner_only: bool
    handler: CommandHandler


_REGISTRY: dict[str, Command] = {}
_ALIAS_INDEX: dict[str, str] = {}


def register(command: Command) -> Command:
    """Register a command and its aliases. Idempotent for re-imports."""
    _REGISTRY[command.name] = command
    for alias in (command.name, *command.aliases):
        _ALIAS_INDEX[alias.lower()] = command.name
    return command


def list_commands() -> list[Command]:
    return sorted(_REGISTRY.values(), key=lambda c: c.name)


def _strip_prefix(text: str) -> str | None:
    body = text.lstrip()
    for prefix in PREFIXES:
        if body.startswith(prefix):
            return body[len(prefix):]
    return None


_TOKEN_RE = re.compile(r"^([a-zA-Z][\w-]*)(?:\s+(.*))?$", re.DOTALL)


def detect(text: str) -> CommandMatch | None:
    """Return a :class:`CommandMatch` if ``text`` starts with a known command.

    Matching is case-insensitive on the command name; arguments preserve
    their original casing (handlers like ``/model`` care).
    """
    if not text:
        return None
    body = _strip_prefix(text)
    if body is None:
        return None
    m = _TOKEN_RE.match(body.strip())
    if not m:
        return None
    name = m.group(1).lower()
    args = (m.group(2) or "").strip()
    canonical = _ALIAS_INDEX.get(name)
    if canonical is None:
        # Unknown command — still treat as a match so the dispatcher can return
        # a friendly "unknown command" message instead of routing to the LLM.
        return CommandMatch(name=name, args=args, raw=text)
    cmd = _REGISTRY[canonical]
    if args and not cmd.accepts_args:
        # OpenClaw is strict about this; handlers that don't take args should
        # not silently swallow them.
        return CommandMatch(name=canonical, args="", raw=text)
    return CommandMatch(name=canonical, args=args, raw=text)


def is_abort_trigger(text: str) -> bool:
    """``/stop`` ``!cancel`` ``stop`` (bare word) all count as aborts."""
    if not text:
        return False
    body = _strip_prefix(text) or text
    head = body.strip().split(maxsplit=1)
    if not head:
        return False
    return head[0].lower() in ABORT_TRIGGERS


def dispatch(match: CommandMatch, ctx: CommandContext) -> CommandResult:
    """Execute the matched command. Caller is responsible for owner gating."""
    canonical = _ALIAS_INDEX.get(match.name)
    if canonical is None:
        return CommandResult(
            text=f"Unknown command `/{match.name}`. Try `/help`.",
            handled=True,
        )
    cmd = _REGISTRY[canonical]
    if cmd.owner_only and not ctx.is_owner:
        return CommandResult(
            text=f"`/{cmd.name}` is owner-only.",
            handled=True,
        )
    try:
        return cmd.handler(ctx)
    except Exception as exc:  # noqa: BLE001 -- surface everything as text
        logger.exception("command handler failed: %s", cmd.name)
        return CommandResult(text=f"`/{cmd.name}` failed: {exc}", handled=True)


# ---------------------------------------------------------------------------
# Built-in handlers
# ---------------------------------------------------------------------------
def _help(ctx: CommandContext) -> CommandResult:
    lines = ["Available commands:"]
    for cmd in list_commands():
        if cmd.owner_only and not ctx.is_owner:
            continue
        lines.append(f"  /{cmd.name} — {cmd.description}")
    return CommandResult(text="\n".join(lines))


def _status(ctx: CommandContext) -> CommandResult:
    """Lightweight per-session status. Heavy checks live in `/doctor`."""
    from core.models import Message, Session

    try:
        session = Session.objects.get(id=ctx.session_id)
    except Session.DoesNotExist:
        return CommandResult(text=f"No session {ctx.session_id}.")
    n_msgs = Message.objects.filter(session=session).count()
    last = (
        Message.objects.filter(session=session).order_by("-created_at").first()
    )
    last_at = last.created_at.isoformat() if last else "—"
    return CommandResult(
        text=(
            f"session={session.id}\n"
            f"source={session.source}\n"
            f"messages={n_msgs}\n"
            f"last_message_at={last_at}\n"
            f"channel={ctx.channel}"
        )
    )


def _stop(_ctx: CommandContext) -> CommandResult:
    """Signal that the next turn should abort. Actual interrupt is graph-side."""
    return CommandResult(
        text="OK, aborting current turn.",
        abort_turn=True,
    )


def _model(ctx: CommandContext) -> CommandResult:
    """Pin the next turn to a specific model: ``/model gemini`` or ``/model gemma``."""
    from core.models import SystemState

    target = ctx.args.strip().lower()
    if target not in {"gemini", "gemma", "ollama", "auto"}:
        return CommandResult(
            text="Usage: `/model gemini | gemma | auto`",
        )
    SystemState.objects.update_or_create(
        key=f"model_pin:{ctx.session_id}",
        defaults={"value": "" if target == "auto" else target},
    )
    return CommandResult(text=f"model pinned to `{target}` for this session.")


def _notes(_ctx: CommandContext) -> CommandResult:
    from memory.models import NoteIndex

    items = list(
        NoteIndex.objects.order_by("-updated_at").values("title", "path")[:10]
    )
    if not items:
        return CommandResult(text="No notes indexed yet.")
    lines = ["Recent notes:"]
    for n in items:
        lines.append(f"  {n['title']}  ({n['path']})")
    return CommandResult(text="\n".join(lines))


def _approve(ctx: CommandContext) -> CommandResult:
    return _decide_approval(ctx, decision="approved")


def _deny(ctx: CommandContext) -> CommandResult:
    return _decide_approval(ctx, decision="denied")


def _decide_approval(ctx: CommandContext, *, decision: str) -> CommandResult:
    """``/approve <request_id>`` or ``/deny <request_id>``."""
    from approval.models import ApprovalRequest

    req_id = ctx.args.strip()
    if not req_id:
        return CommandResult(text=f"Usage: `/{decision[:-1] + 'e'} <request_id>`")
    try:
        req = ApprovalRequest.objects.get(id=req_id)
    except (ApprovalRequest.DoesNotExist, ValueError):
        return CommandResult(text=f"No pending request {req_id}.")
    if req.status != ApprovalRequest.Status.PENDING:
        return CommandResult(text=f"Request {req_id} is already {req.status}.")
    req.status = (
        ApprovalRequest.Status.APPROVED
        if decision == "approved"
        else ApprovalRequest.Status.DENIED
    )
    req.save(update_fields=["status"])
    return CommandResult(text=f"{req_id} {decision}.")


def _doctor(_ctx: CommandContext) -> CommandResult:
    from api.doctor import run_checks

    report = run_checks()
    lines = [f"{check['name']}: {check['status']}" for check in report["checks"]]
    lines.append(f"overall: {report['status']}")
    return CommandResult(text="\n".join(lines))


# ---------------------------------------------------------------------------
# Registration (kept at module bottom so handlers are defined first)
# ---------------------------------------------------------------------------
register(Command(
    name="help",
    aliases=("h", "?"),
    description="List available commands.",
    accepts_args=False,
    owner_only=False,
    handler=_help,
))
register(Command(
    name="status",
    aliases=(),
    description="Per-session message count + last activity.",
    accepts_args=False,
    owner_only=False,
    handler=_status,
))
register(Command(
    name="stop",
    aliases=("abort", "cancel"),
    description="Abort the current agent turn.",
    accepts_args=False,
    owner_only=True,
    handler=_stop,
))
register(Command(
    name="model",
    aliases=(),
    description="Pin model: /model gemini | gemma | auto.",
    accepts_args=True,
    owner_only=True,
    handler=_model,
))
register(Command(
    name="notes",
    aliases=("n",),
    description="List the 10 most recently updated notes.",
    accepts_args=False,
    owner_only=True,
    handler=_notes,
))
register(Command(
    name="approve",
    aliases=("a",),
    description="Approve a pending action: /approve <request_id>.",
    accepts_args=True,
    owner_only=True,
    handler=_approve,
))
register(Command(
    name="deny",
    aliases=("d",),
    description="Deny a pending action: /deny <request_id>.",
    accepts_args=True,
    owner_only=True,
    handler=_deny,
))
register(Command(
    name="doctor",
    aliases=("health",),
    description="Run system health checks (DB, Redis, Ollama, Gemini, pgvector).",
    accepts_args=False,
    owner_only=True,
    handler=_doctor,
))
