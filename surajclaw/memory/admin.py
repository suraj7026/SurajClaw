from django.contrib import admin

from memory.models import Entity, NoteIndex, SessionEmbedding


@admin.register(Entity)
class EntityAdmin(admin.ModelAdmin):
    list_display = ("entity_type", "name", "last_updated")
    list_filter = ("entity_type",)
    search_fields = ("name",)


@admin.register(NoteIndex)
class NoteIndexAdmin(admin.ModelAdmin):
    list_display = ("title", "filename", "updated_at")
    search_fields = ("title", "filename")


@admin.register(SessionEmbedding)
class SessionEmbeddingAdmin(admin.ModelAdmin):
    list_display = ("session", "created_at")
    search_fields = ("summary_text",)
