"""Feeds app: RSS subscriptions + web-scrape configs + their results."""
from __future__ import annotations

import uuid

from django.db import models


class RSSFeed(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    url = models.URLField(unique=True, max_length=500)
    is_active = models.BooleanField(default=True)
    last_polled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "feeds_rss_feed"
        ordering = ["title"]

    def __str__(self) -> str:
        return self.title


class RSSItem(models.Model):
    """A single item from an RSSFeed.

    Flag `is_new=True` is cleared once the daily briefing includes the item,
    so the briefing only surfaces un-seen content.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    feed = models.ForeignKey(RSSFeed, on_delete=models.CASCADE, related_name="items")
    title = models.CharField(max_length=500)
    url = models.URLField(max_length=500)
    snippet = models.TextField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    is_new = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "feeds_rss_item"
        ordering = ["-published_at", "-created_at"]
        indexes = [
            models.Index(fields=["feed", "published_at"]),
            models.Index(fields=["is_new"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["feed", "url"], name="uniq_feed_item_url"
            ),
        ]

    def __str__(self) -> str:
        return self.title


class ScrapeConfig(models.Model):
    """Named scrape target: URL + CSS selector + cron."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=128, unique=True)
    url = models.URLField(max_length=500)
    css_selector = models.CharField(max_length=500)
    cron_expression = models.CharField(max_length=64, default="0 */6 * * *")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "feeds_scrape_config"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class ScrapeResult(models.Model):
    """Snapshot of a scrape run; `has_changed=True` when hash differs from
    the previous row for the same config."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    config = models.ForeignKey(
        ScrapeConfig, on_delete=models.CASCADE, related_name="results"
    )
    content = models.TextField()
    content_hash = models.CharField(max_length=64)
    has_changed = models.BooleanField(default=False)
    scraped_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "feeds_scrape_result"
        ordering = ["-scraped_at"]
        indexes = [
            models.Index(fields=["config", "scraped_at"]),
            models.Index(fields=["has_changed"]),
        ]

    def __str__(self) -> str:
        return f"ScrapeResult({self.config.name}@{self.scraped_at:%Y-%m-%d %H:%M})"
