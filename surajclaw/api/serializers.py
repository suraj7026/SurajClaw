"""DRF serializers for SurajClaw dashboard APIs.

Each serializer is intentionally narrow: only fields that the dashboard
actually renders are exposed. Vector embeddings are *never* serialized to
the client (they're large and meaningless without the index).
"""
from __future__ import annotations

from rest_framework import serializers

from core.models import (
    AuditLog,
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


class SessionSerializer(serializers.ModelSerializer):
    message_count = serializers.IntegerField(read_only=True, required=False)

    class Meta:
        model = Session
        fields = [
            "id",
            "source",
            "started_at",
            "ended_at",
            "summary",
            "is_active",
            "message_count",
        ]


class MessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Message
        fields = [
            "id",
            "session",
            "role",
            "content",
            "model_used",
            "tokens_used",
            "created_at",
        ]


class TaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = Task
        fields = [
            "id",
            "session",
            "source",
            "request",
            "result",
            "tools_used",
            "tokens_used",
            "status",
            "created_at",
            "completed_at",
        ]


class CronJobSerializer(serializers.ModelSerializer):
    class Meta:
        model = CronJob
        fields = [
            "id",
            "name",
            "description",
            "schedule_kind",
            "schedule_value",
            "timezone",
            "stagger_seconds",
            "prompt",
            "light_context",
            "tools_allow",
            "delivery_mode",
            "delivery_channel",
            "delivery_to",
            "delivery_webhook_url",
            "fail_alert_after",
            "fail_alert_cooldown_seconds",
            "consecutive_failures",
            "status",
            "next_run_at",
            "last_run_at",
            "last_run_status",
            "running_since",
            "created_at",
            "updated_at",
        ]


class CronRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = CronRun
        fields = [
            "id",
            "job",
            "status",
            "started_at",
            "finished_at",
            "duration_ms",
            "model_used",
            "provider_used",
            "input_tokens",
            "output_tokens",
            "summary",
            "error_text",
            "delivery_status",
        ]


class FutureQueueSerializer(serializers.ModelSerializer):
    class Meta:
        model = FutureQueue
        fields = [
            "id",
            "intent",
            "due_at",
            "trigger_type",
            "status",
            "source_session",
            "created_at",
        ]


class SystemStateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SystemState
        fields = ["key", "value", "updated_at"]


class DreamLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = DreamLog
        fields = [
            "id",
            "trigger",
            "sessions_processed",
            "entities_merged",
            "entities_pruned",
            "notes_updated",
            "duration_seconds",
            "summary",
            "created_at",
        ]


class AuditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditLog
        fields = "__all__"


class EntitySerializer(serializers.ModelSerializer):
    """Entity facts. Embedding column intentionally omitted (large + opaque)."""

    class Meta:
        model = Entity
        fields = [
            "id",
            "entity_type",
            "name",
            "attributes",
            "source_session",
            "last_updated",
        ]


class NoteIndexSerializer(serializers.ModelSerializer):
    class Meta:
        model = NoteIndex
        fields = [
            "id",
            "title",
            "filename",
            "content_preview",
            "source_session",
            "created_at",
            "updated_at",
        ]


class SessionEmbeddingSerializer(serializers.ModelSerializer):
    class Meta:
        model = SessionEmbedding
        fields = [
            "id",
            "session",
            "summary_text",
            "created_at",
        ]


class SimilaritySearchRequestSerializer(serializers.Serializer):
    query = serializers.CharField()
    target = serializers.ChoiceField(
        choices=("entities", "notes", "sessions"),
        default="notes",
    )
    limit = serializers.IntegerField(min_value=1, max_value=50, default=5)


class SimilarityHitSerializer(serializers.Serializer):
    """One hit in a similarity search response."""

    id = serializers.UUIDField()
    title = serializers.CharField()
    snippet = serializers.CharField(allow_blank=True)
    distance = serializers.FloatField()
    kind = serializers.CharField()


class GoogleAccountSerializer(serializers.Serializer):
    label = serializers.CharField()
    email = serializers.CharField(allow_blank=True, required=False)
    scopes = serializers.ListField(child=serializers.CharField(), required=False)
    expires_at = serializers.DateTimeField(allow_null=True, required=False)
    token_path = serializers.CharField()


class MetricsSerializer(serializers.Serializer):
    """Aggregated dashboard metrics. Recomputed on each request."""

    active_sessions = serializers.IntegerField()
    active_jobs = serializers.IntegerField()
    pending_queue = serializers.IntegerField()
    total_tasks = serializers.IntegerField()
    success_rate = serializers.FloatField()
    token_throughput = serializers.IntegerField()
    total_messages = serializers.IntegerField()
    total_entities = serializers.IntegerField()
    total_notes = serializers.IntegerField()
    last_dream_at = serializers.DateTimeField(allow_null=True)
