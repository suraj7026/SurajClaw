"""DRF ViewSets backing the SurajClaw dashboard.

Read-mostly. Anything that mutates server state (manual cron trigger, queue
delete, account disconnect) is exposed as an explicit ``@action`` so the
URL stays predictable and we can require POST/DELETE per operation.

The `metrics` view is intentionally a single endpoint (not a model) because
the dashboard wants one round-trip for everything in the top status bar.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from django.db.models import Count
from django.utils import timezone
from rest_framework import filters, mixins, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from api.serializers import (
    CronJobSerializer,
    CronRunSerializer,
    DreamLogSerializer,
    EntitySerializer,
    FutureQueueSerializer,
    MessageSerializer,
    MetricsSerializer,
    NoteIndexSerializer,
    SessionEmbeddingSerializer,
    SessionSerializer,
    SimilarityHitSerializer,
    SimilaritySearchRequestSerializer,
    SystemStateSerializer,
    TaskSerializer,
)
from core.models import (
    CronJob,
    CronRun,
    DreamLog,
    FutureQueue,
    Message,
    Session,
    SystemState,
    Task,
)
from memory.models import Entity, NoteIndex, SessionEmbedding

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Sessions / messages
# ---------------------------------------------------------------------------
class SessionViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """List + retrieve conversation sessions, with filterable source/active."""

    serializer_class = SessionSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["source", "is_active"]
    ordering_fields = ["started_at", "ended_at"]
    ordering = ["-started_at"]

    def get_queryset(self):
        return Session.objects.annotate(message_count=Count("messages"))

    @action(detail=True, methods=["get"], url_path="messages")
    def messages(self, request: Request, pk: str | None = None) -> Response:
        msgs = Message.objects.filter(session_id=pk).order_by("created_at")
        page = self.paginate_queryset(msgs)
        serializer = MessageSerializer(page or msgs, many=True)
        return self.get_paginated_response(serializer.data) if page is not None else Response(serializer.data)


class MessageViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = MessageSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["session", "role"]
    ordering = ["-created_at"]

    def get_queryset(self):
        return Message.objects.all()


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------
class TaskViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = TaskSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["status", "source", "session"]
    ordering = ["-created_at"]

    def get_queryset(self):
        return Task.objects.all()


# ---------------------------------------------------------------------------
# Cron jobs + runs
# ---------------------------------------------------------------------------
class CronJobViewSet(viewsets.ModelViewSet):
    serializer_class = CronJobSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["status", "schedule_kind"]
    ordering_fields = ["next_run_at", "last_run_at", "name"]
    ordering = ["next_run_at"]

    def get_queryset(self):
        return CronJob.objects.all()

    @action(detail=True, methods=["get"], url_path="runs")
    def runs(self, request: Request, pk: str | None = None) -> Response:
        runs = CronRun.objects.filter(job_id=pk).order_by("-started_at")
        page = self.paginate_queryset(runs)
        serializer = CronRunSerializer(page or runs, many=True)
        return self.get_paginated_response(serializer.data) if page is not None else Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="trigger")
    def trigger(self, request: Request, pk: str | None = None) -> Response:
        """Manually fire a cron job by setting next_run_at to now.

        The Celery `cron_job_poll` beat task will pick it up on its next
        tick. We don't directly call the runner here because that would
        block the request and bypass the same concurrency guard the poller
        uses.
        """
        try:
            job = CronJob.objects.get(pk=pk)
        except CronJob.DoesNotExist:
            return Response({"detail": "not found"}, status=status.HTTP_404_NOT_FOUND)
        job.next_run_at = timezone.now()
        job.status = CronJob.Status.ACTIVE
        job.save(update_fields=["next_run_at", "status", "updated_at"])
        return Response({"status": "triggered", "next_run_at": job.next_run_at})


class CronRunViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = CronRunSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["job", "status"]
    ordering = ["-started_at"]

    def get_queryset(self):
        return CronRun.objects.all()


# ---------------------------------------------------------------------------
# Future queue
# ---------------------------------------------------------------------------
class FutureQueueViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """List/cancel deferred intents. Delete = mark cancelled, not hard-delete."""

    serializer_class = FutureQueueSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["status", "trigger_type"]
    ordering = ["due_at"]

    def get_queryset(self):
        return FutureQueue.objects.all()

    def perform_destroy(self, instance: FutureQueue) -> None:
        instance.status = FutureQueue.Status.CANCELLED
        instance.save(update_fields=["status"])


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------
class EntityViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = EntitySerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["entity_type"]
    ordering = ["-last_updated"]

    def get_queryset(self):
        return Entity.objects.all()


class NoteIndexViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = NoteIndexSerializer
    permission_classes = [IsAuthenticated]
    ordering = ["-updated_at"]

    def get_queryset(self):
        return NoteIndex.objects.all()


class SessionEmbeddingViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = SessionEmbeddingSerializer
    permission_classes = [IsAuthenticated]
    ordering = ["-created_at"]

    def get_queryset(self):
        return SessionEmbedding.objects.all()


# ---------------------------------------------------------------------------
# System state, dream logs
# ---------------------------------------------------------------------------
class SystemStateViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = SystemStateSerializer
    permission_classes = [IsAuthenticated]
    ordering = ["-updated_at"]
    lookup_field = "key"
    # Allow non-slug keys like `model_pin:<uuid>`.
    lookup_value_regex = "[^/]+"

    def get_queryset(self):
        return SystemState.objects.all()


class DreamLogViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = DreamLogSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["trigger"]
    ordering = ["-created_at"]

    def get_queryset(self):
        return DreamLog.objects.all()


# ---------------------------------------------------------------------------
# Aggregate metrics + similarity search (function views)
# ---------------------------------------------------------------------------
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def metrics_view(_request: Request) -> Response:
    """One-shot aggregate for the dashboard top bar.

    Recomputed each call; cheap because we only count rows. If this becomes
    slow we should cache for a few seconds, not paginate.
    """
    now = timezone.now()
    last_24h = now - timedelta(hours=24)

    total_tasks = Task.objects.count()
    successful = Task.objects.filter(status=Task.Status.DONE).count()
    success_rate = (successful / total_tasks * 100.0) if total_tasks else 100.0

    # Token throughput: sum of tokens used in tasks completed in the last 24h.
    recent_tokens = (
        Task.objects.filter(completed_at__gte=last_24h, tokens_used__isnull=False)
        .values_list("tokens_used", flat=True)
    )
    token_throughput = sum(recent_tokens) if recent_tokens else 0

    last_dream = DreamLog.objects.order_by("-created_at").first()

    payload = {
        "active_sessions": Session.objects.filter(is_active=True).count(),
        "active_jobs": CronJob.objects.filter(status=CronJob.Status.ACTIVE).count(),
        "pending_queue": FutureQueue.objects.filter(status=FutureQueue.Status.PENDING).count(),
        "total_tasks": total_tasks,
        "success_rate": round(success_rate, 2),
        "token_throughput": token_throughput,
        "total_messages": Message.objects.count(),
        "total_entities": Entity.objects.count(),
        "total_notes": NoteIndex.objects.count(),
        "last_dream_at": last_dream.created_at if last_dream else None,
    }
    return Response(MetricsSerializer(payload).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def similarity_search_view(request: Request) -> Response:
    """Run a pgvector cosine-distance lookup against the chosen target store.

    Embedding generation can be slow (Ollama call); the timeout in
    ``memory.services.embed_text`` already protects us from hanging
    forever. On failure, returns an empty hits list rather than 500.
    """
    serializer = SimilaritySearchRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    query = serializer.validated_data["query"]
    target = serializer.validated_data["target"]
    limit = serializer.validated_data["limit"]

    try:
        from memory.services import (
            semantic_search_entities,
            semantic_search_notes,
            semantic_search_sessions,
        )
    except ImportError as exc:
        logger.warning("memory.services unavailable: %s", exc)
        return Response({"hits": [], "target": target})

    hits = []
    if target == "notes":
        for n in semantic_search_notes(query, limit):
            hits.append({
                "id": n.id,
                "title": n.title,
                "snippet": (n.content_preview or "")[:200],
                "distance": float(getattr(n, "distance", 0.0)),
                "kind": "note",
            })
    elif target == "entities":
        for e in semantic_search_entities(query, limit):
            hits.append({
                "id": e.id,
                "title": f"{e.entity_type}:{e.name}",
                "snippet": str(e.attributes)[:200],
                "distance": float(getattr(e, "distance", 0.0)),
                "kind": "entity",
            })
    elif target == "sessions":
        for s in semantic_search_sessions(query, limit):
            hits.append({
                "id": s.id,
                "title": f"Session {s.session_id}",
                "snippet": (s.summary_text or "")[:200],
                "distance": float(getattr(s, "distance", 0.0)),
                "kind": "session",
            })

    return Response({
        "target": target,
        "query": query,
        "hits": SimilarityHitSerializer(hits, many=True).data,
    })
