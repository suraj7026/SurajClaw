from django.contrib import admin

from feeds.models import RSSFeed, RSSItem, ScrapeConfig, ScrapeResult


@admin.register(RSSFeed)
class RSSFeedAdmin(admin.ModelAdmin):
    list_display = ("title", "url", "is_active", "last_polled_at")
    list_filter = ("is_active",)
    search_fields = ("title", "url")


@admin.register(RSSItem)
class RSSItemAdmin(admin.ModelAdmin):
    list_display = ("title", "feed", "published_at", "is_new")
    list_filter = ("feed", "is_new")
    search_fields = ("title",)


@admin.register(ScrapeConfig)
class ScrapeConfigAdmin(admin.ModelAdmin):
    list_display = ("name", "url", "is_active", "cron_expression")
    list_filter = ("is_active",)
    search_fields = ("name", "url")


@admin.register(ScrapeResult)
class ScrapeResultAdmin(admin.ModelAdmin):
    list_display = ("config", "has_changed", "scraped_at")
    list_filter = ("has_changed", "config")
