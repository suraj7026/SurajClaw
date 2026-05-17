"""DRF views for the Kanban queue.

Authenticated endpoints:

    GET    /api/kanban/tasks/              -- list (filterable by ?status=...)
    POST   /api/kanban/tasks/              -- create  {title, prompt, ...}
    GET    /api/kanban/tasks/<id>/         -- retrieve
    POST   /api/kanban/tasks/<id>/cancel/  -- cancel a queued/claimed task
"""
from __future__ import annotations

from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from kanban.models import KanbanTask
from kanban.services import cancel as cancel_task


class KanbanTaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = KanbanTask
        fields = "__all__"
        read_only_fields = (
            "id",
            "status",
            "claim_id",
            "claimed_at",
            "heartbeat_at",
            "started_at",
            "finished_at",
            "result",
            "error_text",
            "attempts",
            "created_at",
            "updated_at",
        )


class KanbanTaskViewSet(viewsets.ModelViewSet):
    serializer_class = KanbanTaskSerializer
    queryset = KanbanTask.objects.all()
    filterset_fields = ["status", "agent_id", "created_by"]
    ordering_fields = ["priority", "created_at", "finished_at"]

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        if cancel_task(pk):
            return Response({"status": "cancelled"})
        return Response(
            {"detail": "task not cancellable (already running or finished)"},
            status=status.HTTP_409_CONFLICT,
        )
