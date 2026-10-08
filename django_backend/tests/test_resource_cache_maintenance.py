from datetime import timedelta
from io import StringIO
import json
from uuid import uuid4

import pytest
from django.core.management import call_command
from django.db.models import QuerySet
from django.utils import timezone

from nassav.resource_cache_maintenance import DjangoProviderCacheMaintenance
from nassav.models import ResourceMetadataCache, ResourcePlaybackCache

pytestmark = pytest.mark.django_db


def record(model, avid, **values):
    return model.objects.create(
        avid=avid,
        provider_kind="source",
        provider_name="fixture",
        scope_key="scope",
        variant_key="variant",
        **values,
    )


def test_cleanup_is_bounded_dry_run_preserves_fresh_and_live_claims():
    now = timezone.now()
    for avid in ("old-1", "old-2"):
        record(ResourceMetadataCache, avid, last_used_at=now - timedelta(days=91))
    hot = record(ResourceMetadataCache, "hot")
    live = record(
        ResourcePlaybackCache,
        "live",
        fresh_until=now - timedelta(days=2),
        fetch_owner=uuid4(),
        fetch_lease_until=now + timedelta(minutes=1),
    )
    expired = record(
        ResourcePlaybackCache, "expired", fresh_until=now - timedelta(days=2)
    )
    service = DjangoProviderCacheMaintenance(now=lambda: now)
    assert service.purge(limit=1) == {"metadata": 1, "playback": 1}
    assert ResourceMetadataCache.objects.count() == 3
    assert service.purge(limit=1, apply=True) == {"metadata": 1, "playback": 1}
    assert ResourceMetadataCache.objects.filter(pk=hot.pk).exists()
    assert ResourcePlaybackCache.objects.filter(pk=live.pk).exists()
    assert not ResourcePlaybackCache.objects.filter(pk=expired.pk).exists()
    with pytest.raises(ValueError):
        service.purge(limit=0)


def test_claim_renewed_between_selection_and_delete_is_preserved(monkeypatch):
    now = timezone.now()
    row = record(ResourcePlaybackCache, "raced", fresh_until=now - timedelta(days=2))
    original = QuerySet.delete

    def renew(query):
        if query.model is ResourcePlaybackCache:
            ResourcePlaybackCache.objects.filter(pk=row.pk).update(
                fetch_owner=uuid4(), fetch_lease_until=now + timedelta(minutes=1)
            )
        return original(query)

    monkeypatch.setattr(QuerySet, "delete", renew)
    assert (
        DjangoProviderCacheMaintenance(now=lambda: now).purge(apply=True)["playback"]
        == 0
    )
    assert ResourcePlaybackCache.objects.filter(pk=row.pk).exists()


def test_command_only_returns_counts_and_defaults_to_preview():
    record(
        ResourceMetadataCache, "old", last_used_at=timezone.now() - timedelta(days=91)
    )
    output = StringIO()
    call_command("provider_cache", stdout=output)
    result = json.loads(output.getvalue())
    assert result["applied"] is False
    assert result["statistics"]["metadata"]["total"] == 1
    assert result["cleanup"]["metadata"] == 1
    assert "payload" not in output.getvalue()
    call_command("provider_cache", apply=True, stdout=StringIO())
    assert ResourceMetadataCache.objects.count() == 0


def test_beat_task_uses_bounded_cleanup_and_stable_name():
    from nassav.tasks import cleanup_provider_cache
    from django.conf import settings

    assert cleanup_provider_cache.name == "nassav.tasks.cleanup_provider_cache"
    assert (
        settings.CELERY_BEAT_SCHEDULE["cleanup-provider-cache"]["task"]
        == cleanup_provider_cache.name
    )
    assert cleanup_provider_cache.run() == {"metadata": 0, "playback": 0}
