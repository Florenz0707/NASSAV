"""Short pool-fenced grace markers, independent of task/file execution."""

from datetime import timedelta
from django.db import connection
from django.db.models import Q
from django.utils import timezone
from nassav.resource_version_models import ResourceVersion


def schedule_unused_versions(pool, *, grace=timedelta(hours=24), now=None):
    """Caller holds the pool write fence. Pointers alone are not permanent readers."""
    if not connection.in_atomic_block:
        raise RuntimeError("GC scheduling requires the pool transaction")
    now = now or timezone.now()
    versions = ResourceVersion.objects.filter(pool=pool, state__in=["ready", "retired"])
    held = Q(metadata_holders__isnull=False) | Q(video_holders__isnull=False)
    versions.filter(held).update(gc_after=None)
    return (
        versions.exclude(held)
        .filter(gc_after__isnull=True)
        .update(gc_after=now + grace)
    )
