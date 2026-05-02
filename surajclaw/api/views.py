"""REST API views. Kept thin; business logic lives in services/tools."""
from __future__ import annotations

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response


@api_view(["GET"])
@permission_classes([AllowAny])
def health(_request: Request) -> Response:
    """Liveness probe. Used by Nginx/systemd checks."""
    return Response({"status": "ok"})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_agents(_request: Request) -> Response:
    """List directly available specialized agents."""
    from agents.registry import list_agents as _list_agents

    agents = [
        {
            "id": agent.id,
            "display_name": agent.display_name,
            "description": agent.description,
            "direct_access": agent.direct_access,
            "delegatable": agent.delegatable,
            "allowed_tools": sorted(agent.allowed_tools),
        }
        for agent in _list_agents()
    ]
    return Response({"agents": agents})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def invoke_agent(request: Request, agent_id: str) -> Response:
    """Invoke one specialized agent graph directly."""
    from agents.invocation import invoke_agent as _invoke_agent
    from agents.registry import can_invoke_directly
    from agents.types import AgentInvocation

    try:
        allowed = can_invoke_directly(agent_id)
    except LookupError as exc:
        return Response({"detail": str(exc)}, status=404)
    if not allowed:
        return Response({"detail": f"agent {agent_id} cannot be invoked directly"}, status=403)

    task = str(request.data.get("task", "")).strip()
    if not task:
        return Response({"detail": "task is required"}, status=400)
    session_id = str(request.data.get("session_id") or "api")
    result = _invoke_agent(
        AgentInvocation(
            session_id=session_id,
            source="api",
            agent_id=agent_id,
            task=task,
            account_label=request.data.get("account_label"),
            context=request.data.get("context") or {},
        )
    )
    return Response(result.__dict__)
