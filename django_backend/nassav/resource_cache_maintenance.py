"""Bounded eviction of disposable facts; never manages library files or task assets."""

from datetime import timedelta

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from nassav.resource_cache_models import ResourceMetadataCache, ResourcePlaybackCache


class DjangoProviderCacheMaintenance:
    def __init__(self, *, now=timezone.now):
        self.now = now

    def _eligible(self, model, now):
        policy = settings.RESOURCE_CACHE_POLICY
        inactive = Q(fetch_owner__isnull=True) | Q(fetch_lease_until__lte=now)
        if model is ResourceMetadataCache:
            stale = Q(
                last_used_at__lte=now - timedelta(days=policy["MetadataRetentionDays"])
            )
        else:
            cutoff = now - timedelta(hours=policy["PlaybackGraceHours"])
            stale = Q(fresh_until__lte=cutoff) | Q(
                fresh_until__isnull=True, last_used_at__lte=cutoff
            )
        return model.objects.filter(inactive, stale)

    def statistics(self):
        now = self.now()
        result = {}
        for name, model in (
            ("metadata", ResourceMetadataCache),
            ("playback", ResourcePlaybackCache),
        ):
            result[name] = {
                "total": model.objects.count(),
                "fresh": model.objects.filter(fresh_until__gt=now)
                .exclude(payload={})
                .count(),
                "leased": model.objects.filter(
                    fetch_owner__isnull=False, fetch_lease_until__gt=now
                ).count(),
                "eligible_for_cleanup": self._eligible(model, now).count(),
            }
        return result

    def purge(self, *, apply=False, limit=None):
        limit = (
            settings.RESOURCE_CACHE_POLICY["CleanupBatchSize"]
            if limit is None
            else limit
        )
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 5000
        ):
            raise ValueError("Cache cleanup limit must be between 1 and 5000")
        now = self.now()
        result = {}
        for name, model in (
            ("metadata", ResourceMetadataCache),
            ("playback", ResourcePlaybackCache),
        ):
            eligible = self._eligible(model, now)
            ids = list(eligible.order_by("pk").values_list("pk", flat=True)[:limit])
            # Recheck all eviction conditions in the delete, including claims renewed since selection.
            result[name] = (
                eligible.filter(pk__in=ids).delete()[0] if apply else len(ids)
            )
        return result
