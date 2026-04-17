from django.contrib import admin

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


@admin.register(CronJob)
class CronJobAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "schedule_kind",
        "schedule_value",
        "status",
        "next_run_at",
        "last_run_at",
        "last_run_status",
        "consecutive_failures",
    )
    list_filter = ("status", "schedule_kind", "delivery_mode")
    search_fields = ("name", "description", "prompt")
    ordering = ("next_run_at",)


@admin.register(CronRun)
class CronRunAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "job",
        "status",
        "started_at",
        "duration_ms",
        "model_used",
        "delivery_status",
    )
    list_filter = ("status", "model_used")
    search_fields = ("summary", "error_text")
    ordering = ("-started_at",)
    readonly_fields = tuple(f.name for f in CronRun._meta.fields)


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
