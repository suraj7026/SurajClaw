"""Agent registry for built-in and session-scoped specialized agents."""
from __future__ import annotations

from django.conf import settings

from agents.types import AgentDefinition


_CUSTOM_AGENTS: dict[str, AgentDefinition] = {}


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
    from agents.subgraphs.code_executor import build_code_executor_graph
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
            system_prompt="You are SurajClaw's main orchestrator.",
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
            system_prompt="You are SurajClaw's General Agent supervisor.",
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
            system_prompt="Operate Google Workspace APIs safely. Gmail is read-only.",
            default_model_provider=default_provider,
            allowed_tools=frozenset({
                "google.accounts.list",
                "google.gmail.search_messages",
                "google.gmail.get_message",
                "google.gmail.list_threads",
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
            system_prompt="Execute and debug code in a sandbox. Never run on the host shell.",
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
            system_prompt="Research and maintain concise Markdown notes with citations when available.",
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
    }
