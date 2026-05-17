from django.contrib import admin

from kanban.models import KanbanTask


@admin.register(KanbanTask)
class KanbanTaskAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "status",
        "priority",
        "attempts",
        "agent_id",
        "model_provider",
        "created_at",
        "finished_at",
    )
    list_filter = ("status", "agent_id")
    search_fields = ("title", "prompt", "created_by")
    readonly_fields = (
        "id",
        "claim_id",
        "claimed_at",
        "heartbeat_at",
        "started_at",
        "finished_at",
        "attempts",
        "created_at",
        "updated_at",
    )
