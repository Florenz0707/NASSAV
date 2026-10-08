"""Disposable provider facts, independent of library resources and task assets."""

from django.db import models
from django.utils import timezone


class ProviderCacheRecord(models.Model):
    avid = models.CharField(max_length=50)
    provider_kind = models.CharField(max_length=16)
    provider_name = models.CharField(max_length=64)
    scope_key = models.CharField(max_length=64)
    variant_key = models.CharField(max_length=64)
    payload = models.JSONField(default=dict)
    validated_fields = models.JSONField(default=list)
    parser_version = models.CharField(max_length=64, blank=True)
    fetched_at = models.DateTimeField(null=True)
    fresh_until = models.DateTimeField(null=True)
    last_used_at = models.DateTimeField(default=timezone.now)
    generation = models.PositiveBigIntegerField(default=0)
    fetch_owner = models.UUIDField(null=True)
    fetch_lease_until = models.DateTimeField(null=True)

    class Meta:
        abstract = True


class ResourceMetadataCache(ProviderCacheRecord):
    class Meta:
        db_table = "nassav_resource_metadata_cache"
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "avid",
                    "provider_kind",
                    "provider_name",
                    "scope_key",
                    "variant_key",
                ],
                name="nas_metadata_cache_key_uniq",
            )
        ]
        indexes = [
            models.Index(fields=["last_used_at"], name="nas_metadata_cache_gc_idx")
        ]


class ResourcePlaybackCache(ProviderCacheRecord):
    # No FK to the resource or metadata: each cache can be evicted independently.
    class Meta:
        db_table = "nassav_resource_playback_cache"
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "avid",
                    "provider_kind",
                    "provider_name",
                    "scope_key",
                    "variant_key",
                ],
                name="nas_playback_cache_key_uniq",
            ),
            models.CheckConstraint(
                condition=models.Q(provider_kind="source"),
                name="nas_playback_source_only",
            ),
        ]
        indexes = [
            models.Index(fields=["fresh_until"], name="nas_playback_cache_gc_idx")
        ]
