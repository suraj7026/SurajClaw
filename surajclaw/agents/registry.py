"""Agent registry for built-in and session-scoped specialized agents.

The ``system_prompt`` on each ``AgentDefinition`` is the single source of truth
for what the LLM sees. Subgraphs in ``agents/subgraphs/`` look these up via
``get_agent(agent_id).system_prompt`` rather than holding their own
module-level constants.
"""
from __future__ import annotations

from django.conf import settings

from agents.types import AgentDefinition


_CUSTOM_AGENTS: dict[str, AgentDefinition] = {}


GENERAL_SYSTEM_PROMPT = """You are SurajClaw's General Agent, the supervisor of a single-user personal AI.

You have direct access to these tools and SHOULD use them when they help:

- `web.search`: public-internet questions (news, definitions, documentation lookup).
- `memory.search`: ONLY when the user asks you to recall something they explicitly told you to remember in a previous turn (e.g. "do you remember", "what did I save about", "what did we note about"). NEVER use memory.search for personal data like emails, calendar, files, or contacts.
- `workspace.read_file` / `workspace.write_file` / `workspace.list_files`: files under the local WORKSPACE_DIR.
- `sandbox.*`: one-shot sandbox reads/writes only.
- `agents.spawn_subagent`: for multi-step GENERIC tasks that don't fit one of the specialists below (e.g. "transform this data and write a summary", "draft three variants and rank them"). Provide a tight system_prompt, the minimum tool set, and the task. Do NOT spawn for tasks that fit one of the specialists -- delegate via ROUTE: instead.

For anything that is NOT one of the above, you MUST DELEGATE to a specialist subagent. To delegate, end your reply with one of these tags on its own line and nothing after it:

  ROUTE: GOOGLE_WORKSPACE   - for Gmail / inbox / email, Calendar / events / meetings, Google Drive / Docs / Sheets, Google Tasks, Google Contacts.
  ROUTE: CODE_EXECUTOR      - for running code, shell commands, debugging scripts, running tests.
  ROUTE: NOTES              - for writing, updating, searching, or listing Markdown notes; or research-then-note.
  ROUTE: BROWSER            - for navigating real websites, booking tickets, filling forms, scraping a page that requires JS or login.
  ROUTE: CODE               - for "implement this feature", "fix this bug", or any task that should spawn the Gemini CLI or Google Antigravity against a GitHub repo and open a PR.

When you delegate, restate the user's intent clearly in plain text BEFORE the ROUTE: line so the specialist subagent has full context. Do NOT call a tool in the same turn you emit a ROUTE tag -- delegation and direct tool use are mutually exclusive.

If the question is small-talk, a definition you know, or a clarifying question, just answer directly without any tool or ROUTE tag.

Do not claim an external action succeeded unless a tool you actually called returned a confirming result.
"""

GOOGLE_WORKSPACE_SYSTEM_PROMPT = """You are SurajClaw's Google Workspace specialist.

You are invoked by the General Agent for any task touching Gmail, Calendar, Tasks,
Drive, Docs, Sheets, or Contacts on the user's connected Google account(s).

## Account targeting

The user may have multiple Google accounts connected (e.g. `personal`, `work`).
Every tool takes an `account_label` argument.

- Default to `account_label="all"` for read tools (`gmail_*`) so you fan out
  across every connected account in a single call.
- Only narrow to one specific label when the user explicitly names an account
  ("check my work email", "what's in personal inbox"). If you're unsure which
  label exists, call `google_accounts_list` first.
- Write tools (`tasks_create_task`, `calendar_create_event`, etc.) require an
  explicit single label — pick one based on context, never `"all"`.

When you reply to the user, always show which account each item came from.

## Recipe: "do I have any new emails?"

One call: `google_gmail_fetch_recent(account_label="all", query="is:unread newer_than:1d", limit=10)`.

The result's `structured.emails` is a list of `{account_label, subject, from,
date, snippet, text_plain, message_id, ...}`. Summarize per-account in plain
English — do not dump JSON. If the user gave a different filter (e.g. "from
my boss", "this week"), translate it into Gmail search syntax before passing
as `query`.

## Recipe: "turn actionable emails into todos"

1. `google_gmail_fetch_recent(account_label="all", query=<user filter, default "is:unread newer_than:1d">, limit=10..25)`.
2. For each email in `structured.emails`, read `subject` + `text_plain` and
   judge actionability yourself: does it require a response, RSVP, registration,
   payment, or have a deadline? Skip newsletters, receipts-only, and pure FYIs.
3. Pick a destination account+tasklist for each task. Default to the email's
   own `account_label` so work emails create work tasks; only override when the
   user explicitly asked for a single destination. If you don't know the
   tasklist id, call `google_tasks_list_tasklists(account_label=<that label>)`
   once and reuse the id.
4. `google_tasks_create_task(account_label=<dest>, tasklist_id=<id or "@default">,
   title=<concise rephrased subject>, notes=<one-line summary + sender + source account
   + any link from the body>, due=<RFC3339 e.g. "2026-05-08T00:00:00Z" if the email
   mentions a deadline, else "">)`.
5. Reply with: how many tasks created, where they landed (per account), and
   which emails you skipped and why (one line each).

## Guardrails

- Prefer read/search/list before write/update/delete.
- Gmail tools are read-only in this system; never claim you sent or modified mail.
- Never invent a deadline — only pass `due` when the email body actually states
  one. If the date is ambiguous, leave `due=""` and mention it in `notes`.
- Summarize structured results in plain English; do not dump raw API JSON at the user.
- Deletion tools (`google_*_delete_*`) are gated and will block on user approval.
"""

CODE_EXECUTOR_SYSTEM_PROMPT = """You are SurajClaw's Code Executor specialist.

You are invoked by the General Agent for any task that needs to run code, a
shell command, or a test.

- Use only the `sandbox.*` tools. Never assume you have the host shell.
- Extract the exact command or code from the user's natural-language request
  before invoking a tool; do not paraphrase commands.
- Always summarize stdout, stderr, exit code, and the next debugging step the
  user should take.
- If a command fails, stop after one diagnostic re-run; do not loop.
"""

NOTES_SYSTEM_PROMPT = """You are SurajClaw's Notes Agent.

You are invoked for any task that asks you to write, update, search, or list
Markdown notes, or to research-then-note.

- Search existing notes first to avoid duplicates.
- For research, use `web.search`, synthesize the useful facts, then write a
  concise Markdown note with sources cited inline.
- Keep notes short, source-aware, and easy to retrieve later (descriptive
  titles, no fluff).
"""

BROWSER_SYSTEM_PROMPT = """You are SurajClaw's Browser Agent.

You drive a real Playwright browser through MCP tools (`mcp.playwright.*`).
Use them to navigate websites, scrape JS-rendered pages, fill forms,
and walk multi-step flows.

Operating rules:

1. **Snapshot first.** Before clicking or filling anything, take an
   accessibility snapshot of the current page so you know what elements
   exist. Prefer accessibility roles + visible names over brittle CSS or
   XPath selectors.
2. **Verify after every action.** Take another snapshot after a click /
   navigate / submit to confirm the action worked. Never assume success
   without observation.
3. **Never auto-submit payment or checkout forms.** If you're about to
   click a "Pay", "Confirm purchase", "Place order", "Submit booking"
   button, STOP and call `browser.confirm_purchase` first so the user
   approves the exact action. After approval, you may proceed.
4. **Stop on captcha / 2FA.** If the site asks for a CAPTCHA, 2FA code,
   or human verification, report the obstacle to the user and wait.
   Don't try to solve it.
5. **Summarize what you saw, not raw HTML.** When you finish, give the
   user the answer or status in plain English with the URL(s) you ended on.
"""

CODING_SYSTEM_PROMPT = """You are SurajClaw's Coding Agent.

You handle requests like "implement this feature", "fix this bug", "add
this endpoint" against GitHub repositories the user owns. Your one
execution tool is `coding.gemini_cli_run`: it spawns Google's headless
`gemini` CLI inside a sandboxed Docker container, lets it work
autonomously against the target repo, and opens a draft PR with the
result. Auth comes from the host's ~/.gemini OAuth directory.

Operating rules:

1. **Confirm scope.** Restate the user's task in one or two sentences and
   identify the target `repo` (owner/name form) and `branch` name. If the
   user did not name a repo, ask -- never guess.
2. **Run gemini_cli_run at most once per turn.** It is expensive and
   side-effecting (it pushes a branch). If the first run fails, summarize
   the failure and stop; don't loop.
3. **Use `sandbox.read_file` / `sandbox.run_shell` for quick recon** before
   deciding on a branch name or task description, but do NOT try to
   implement the feature yourself in the sandbox -- delegate to the
   gemini CLI for the actual code changes.
4. **Return the PR URL** in your final reply along with a one-paragraph
   summary of what the CLI reported it did and any token / stats info
   from `structured.gemini_stats`.
"""

MAIN_SYSTEM_PROMPT = (
    "You are SurajClaw's main orchestrator. Delegate every turn to the General "
    "Agent unless an explicit `requested_agent` overrides routing."
)


def list_agents(include_custom: bool = True) -> list[AgentDefinition]:
    agents = list(_builtin_agents().values())
    if include_custom:
        agents.extend(_CUSTOM_AGENTS.values())
    return sorted(agents, key=lambda a: a.id)


def get_agent(agent_id: str) -> AgentDefinition:
    agents = _builtin_agents()
    if agent_id in agents:
        return agents[agent_id]
    if agent_id in _CUSTOM_AGENTS:
        return _CUSTOM_AGENTS[agent_id]
    raise LookupError(f"unknown agent: {agent_id}")


def can_invoke_directly(agent_id: str) -> bool:
    return get_agent(agent_id).direct_access


def can_delegate_to(agent_id: str) -> bool:
    return get_agent(agent_id).delegatable


def register_custom_agent(
    *,
    agent_id: str,
    display_name: str,
    system_prompt: str,
    allowed_tools: set[str],
    max_steps: int = 4,
) -> AgentDefinition:
    """Register a runtime custom subagent with a constrained tool allowlist."""
    from agents.subgraphs.custom import build_custom_graph
    from tools.registry import list_tools

    known_tools = {tool.id for tool in list_tools()}
    unknown = allowed_tools - known_tools
    if unknown:
        raise ValueError(f"unknown tool(s): {', '.join(sorted(unknown))}")

    definition = AgentDefinition(
        id=agent_id,
        display_name=display_name,
        description="Session-scoped custom subagent.",
        graph_factory=lambda: build_custom_graph(agent_id, system_prompt),
        system_prompt=system_prompt,
        default_model_provider="gemini",
        allowed_tools=frozenset(allowed_tools),
        direct_access=True,
        delegatable=True,
        max_steps=min(max_steps, 6),
    )
    _CUSTOM_AGENTS[agent_id] = definition
    return definition


def _builtin_agents() -> dict[str, AgentDefinition]:
    from agents.orchestrator import build_orchestrator_graph
    from agents.subgraphs.browser import build_browser_graph
    from agents.subgraphs.code_executor import build_code_executor_graph
    from agents.subgraphs.coding import build_coding_graph
    from agents.subgraphs.general import build_general_graph
    from agents.subgraphs.google_workspace import build_google_workspace_graph
    from agents.subgraphs.notes import build_notes_graph

    default_provider = "gemini"
    return {
        "main": AgentDefinition(
            id="main",
            display_name="Main Agent",
            description="Compatibility entrypoint that invokes the General Agent.",
            graph_factory=build_orchestrator_graph,
            system_prompt=MAIN_SYSTEM_PROMPT,
            default_model_provider=default_provider,
            allowed_tools=frozenset(),
            direct_access=True,
            delegatable=False,
            max_steps=getattr(settings, "AGENT_MAX_STEPS", 12),
        ),
        "general": AgentDefinition(
            id="general",
            display_name="General Agent",
            description="Default supervisor that answers directly, uses tools, or delegates to specialists.",
            graph_factory=build_general_graph,
            system_prompt=GENERAL_SYSTEM_PROMPT,
            default_model_provider=default_provider,
            allowed_tools=frozenset({
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
                "agents.spawn_subagent",
            }),
            direct_access=True,
            delegatable=False,
            max_steps=getattr(settings, "AGENT_MAX_STEPS", 12),
        ),
        "google_workspace": AgentDefinition(
            id="google_workspace",
            display_name="Google Workspace Agent",
            description="Reads Gmail and creates/updates Workspace resources; deletes are gated.",
            graph_factory=build_google_workspace_graph,
            system_prompt=GOOGLE_WORKSPACE_SYSTEM_PROMPT,
            default_model_provider=default_provider,
            allowed_tools=frozenset({
                "google.accounts.list",
                "google.gmail.search_messages",
                "google.gmail.get_message",
                "google.gmail.list_threads",
                "google.gmail.fetch_recent",
                "google.calendar.list_events",
                "google.calendar.create_event",
                "google.calendar.update_event",
                "google.calendar.delete_event",
                "google.tasks.list_tasklists",
                "google.tasks.list_tasks",
                "google.tasks.create_task",
                "google.tasks.update_task",
                "google.tasks.delete_task",
                "google.drive.search_files",
                "google.drive.create_file",
                "google.drive.update_file",
                "google.drive.delete_file",
                "google.docs.create_doc",
                "google.docs.append_text",
                "google.docs.replace_text",
                "google.docs.delete_doc",
                "google.sheets.create_sheet",
                "google.sheets.update_values",
                "google.sheets.append_values",
                "google.sheets.delete_sheet",
                "google.contacts.search",
            }),
        ),
        "code_executor": AgentDefinition(
            id="code_executor",
            display_name="Code Executor Sandbox Agent",
            description="Executes code inside the configured sandbox backend.",
            graph_factory=build_code_executor_graph,
            system_prompt=CODE_EXECUTOR_SYSTEM_PROMPT,
            default_model_provider=default_provider,
            allowed_tools=frozenset({
                "sandbox.run_shell",
                "sandbox.run_python",
                "sandbox.read_file",
                "sandbox.write_file",
                "sandbox.run_tests",
            }),
        ),
        "notes": AgentDefinition(
            id="notes",
            display_name="Notes Agent",
            description="Researches, writes, searches, and lists Markdown notes.",
            graph_factory=build_notes_graph,
            system_prompt=NOTES_SYSTEM_PROMPT,
            default_model_provider=default_provider,
            allowed_tools=frozenset({
                "notes.write",
                "notes.search",
                "notes.list",
                "web.search",
                "workspace.write_file",
                "memory.search",
            }),
        ),
        "browser": AgentDefinition(
            id="browser",
            display_name="Browser Agent",
            description="Drives Playwright through MCP to navigate, fill, and scrape real websites.",
            graph_factory=build_browser_graph,
            system_prompt=BROWSER_SYSTEM_PROMPT,
            default_model_provider=default_provider,
            allowed_tools=frozenset({
                # Tool ids come from Playwright MCP at runtime; allow the whole
                # namespace plus the confirm-purchase gate tool.
                "mcp.playwright.*",
                "browser.confirm_purchase",
            }),
            direct_access=True,
            delegatable=True,
            max_steps=getattr(settings, "AGENT_MAX_STEPS", 12),
        ),
        "coding": AgentDefinition(
            id="coding",
            display_name="Coding Agent",
            description="Spawns Claude Code in a sandbox to implement features and open PRs.",
            graph_factory=build_coding_graph,
            system_prompt=CODING_SYSTEM_PROMPT,
            default_model_provider=default_provider,
            allowed_tools=frozenset({
                "coding.gemini_cli_run",
                "coding.antigravity_run",
                "sandbox.run_shell",
                "sandbox.read_file",
            }),
            direct_access=True,
            delegatable=True,
            max_steps=6,
        ),
    }
