from django.contrib import admin

from core.models import (
    AuditLog,
    DreamLog,
    FutureQueue,
    Message,
    Session,
    SystemState,
    Task,
)


@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = ("id", "source", "is_active", "started_at", "ended_at")
    list_filter = ("source", "is_active")
    search_fields = ("summary",)
    ordering = ("-started_at",)


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("session", "role", "model_used", "tokens_used", "created_at")
    list_filter = ("role", "model_used")
    search_fields = ("content",)
    ordering = ("-created_at",)


@admin.register(SystemState)
class SystemStateAdmin(admin.ModelAdmin):
    list_display = ("key", "updated_at")
    search_fields = ("key",)


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("id", "source", "status", "created_at", "completed_at")
    list_filter = ("status", "source")
    search_fields = ("request", "result")
    ordering = ("-created_at",)


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("id", "tool_id", "was_gated", "duration_ms", "created_at")
    list_filter = ("tool_id", "was_gated")
    search_fields = ("tool_id", "output_summary")
    ordering = ("-created_at",)
    readonly_fields = tuple(f.name for f in AuditLog._meta.fields)


@admin.register(FutureQueue)
class FutureQueueAdmin(admin.ModelAdmin):
    list_display = ("id", "status", "trigger_type", "due_at", "created_at")
    list_filter = ("status", "trigger_type")
    search_fields = ("intent",)


@admin.register(DreamLog)
class DreamLogAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "trigger",
        "sessions_processed",
        "entities_merged",
        "notes_updated",
        "created_at",
    )
    list_filter = ("trigger",)
    ordering = ("-created_at",)
