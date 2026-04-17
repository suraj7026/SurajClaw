from django.contrib import admin

from custom_tools.models import CustomTool


@admin.register(CustomTool)
class CustomToolAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "is_validated", "created_at")
    list_filter = ("is_active", "is_validated")
    search_fields = ("name", "description")
