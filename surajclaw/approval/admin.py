from django.contrib import admin

from approval.models import ApprovalRequest


@admin.register(ApprovalRequest)
class ApprovalRequestAdmin(admin.ModelAdmin):
    list_display = ("id", "tool_id", "status", "created_at", "expires_at")
    list_filter = ("status", "tool_id")
    search_fields = ("description", "tool_id")
    readonly_fields = ("id", "session", "tool_id", "description", "created_at")
