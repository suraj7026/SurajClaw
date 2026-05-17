"""Inline directive parser for chat messages.

Adapted from OpenClaw's ``src/auto-reply/reply.directive.parse.ts``. A user
can prefix a message with one or more ``!key value`` directives to override
runtime behavior for that single turn:

    !model gemini
    !think high
    !tools web_search,gmail_read
    Summarize my unread emails from this week.

Directives are stripped before the message reaches the LLM, and parsed
values flow into :class:`ParsedDirectives` for the model router and graph
to consume.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# Match a directive at the start of a line: !key value(s) up to newline.
# We intentionally only consume directives at the *very* start of the message
# (and contiguously at line starts) so a stray `!important` mid-paragraph
# doesn't get eaten.
_DIRECTIVE_RE = re.compile(r"^!([a-zA-Z][\w-]*)[ \t]+([^\n]+)(?:\n|$)")

ALLOWED_MODELS = frozenset({
    "gemini",
    "gemini-cli",
    "gemini-oauth",
    "google",
    "google-oauth",
    "auto",
})
ALLOWED_THINKING = frozenset({"low", "medium", "high"})


@dataclass
class ParsedDirectives:
    """Resolved per-turn overrides. All fields are optional.

    The model router merges these *over* its heuristics: an explicit
    ``!model gemini`` always wins, regardless of token budget.
    """

    model: str | None = None
    thinking: str | None = None
    tools_allow: list[str] = field(default_factory=list)
    raw: dict[str, str] = field(default_factory=dict)

    def is_empty(self) -> bool:
        return not (self.model or self.thinking or self.tools_allow)


def parse(message: str) -> tuple[ParsedDirectives, str]:
    """Strip leading ``!key value`` directives and return ``(parsed, body)``.

    Unknown keys are kept in ``raw`` for forward compatibility but do not
    affect routing. Invalid values for known keys are silently ignored
    (router falls back to defaults) — we prefer permissive parsing over
    rejecting otherwise-valid messages.
    """
    parsed = ParsedDirectives()
    if not message:
        return parsed, ""

    remaining = message.lstrip("\n")
    while True:
        m = _DIRECTIVE_RE.match(remaining)
        if not m:
            break
        key = m.group(1).lower()
        value = m.group(2).strip()
        parsed.raw[key] = value
        _apply(parsed, key, value)
        remaining = remaining[m.end():]

    return parsed, remaining.lstrip()


def _apply(parsed: ParsedDirectives, key: str, value: str) -> None:
    if key == "model":
        v = value.lower()
        if v in ALLOWED_MODELS:
            parsed.model = v
    elif key in ("think", "thinking"):
        v = value.lower()
        if v in ALLOWED_THINKING:
            parsed.thinking = v
    elif key == "tools":
        # Comma- or space-separated tool ids.
        items = [t.strip() for t in re.split(r"[,\s]+", value) if t.strip()]
        parsed.tools_allow = items
