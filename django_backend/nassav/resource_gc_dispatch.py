"""Bounded DB-owned dispatch; broker calls never run under a transaction."""

from datetime import timedelta
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone
from nassav.resource_gc import GcDeferred
from nassav.db_retry import retry_sqlite_contention
from nassav.resource_gc_models import ResourceGcJob, ResourceGcCursor
from nassav.resource_version_models import ResourceVersion
from nassav.library_models import ResourcePoolEntry


class GcDispatcher:
    def __init__(
        self, records, send, *, now=timezone.now, cooldown=timedelta(seconds=60)
    ):
        self.records, self.send, self.now, self.cooldown = records, send, now, cooldown

    def recover(self, limit=32):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("Invalid GC dispatch limit")
        now = self.now()
        candidates = list(
            ResourceGcJob.objects.filter(
                Q(state="queued") | Q(state="deleting", lease_until__lte=now)
            )
            .filter(updated_at__lte=now - self.cooldown)
            .order_by("updated_at", "pk")
            .values("pk", "revision")[:limit]
        )
        sent = 0
        for row in candidates:
            if self.reserve_dispatch(row, now):
                try:
                    self.send(str(row["pk"]))
                    sent += 1
                except Exception:
                    # Durable queued/deleting state survives broker outages;
                    # the cooldown prevents all schedulers flooding the queue.
                    pass
        return sent

    def discover(self, limit=32):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("Invalid GC discovery limit")
        now = self.now()
        selected_versions, selected_pools = self.select_candidates(limit, now)
        created = []
        for pool_id, version_id in [
            (row["pool_id"], row["pk"]) for row in selected_versions
        ] + [(value, None) for value in selected_pools]:
            try:
                self.records.schedule(pool_id)
                result = self.records.enqueue(pool_id, version_id)
                if result["job_id"] not in created:
                    created.append(result["job_id"])
            except GcDeferred:
                continue
        return created

    @retry_sqlite_contention
    def reserve_dispatch(self, row, now):
        return (
            ResourceGcJob.objects.filter(
                pk=row["pk"],
                revision=row["revision"],
                updated_at__lte=now - self.cooldown,
            )
            .filter(Q(state="queued") | Q(state="deleting", lease_until__lte=now))
            .update(updated_at=now, revision=F("revision") + 1)
        )

    @retry_sqlite_contention
    def select_candidates(self, limit, now):
        # Selection owns only the cursor fence; pool/user locks are acquired
        # later, after this transaction has closed.
        with transaction.atomic():
            ResourceGcCursor.objects.get_or_create(pk=1)
            ResourceGcCursor.objects.filter(pk=1).update(revision=F("revision") + 1)
            cursor = ResourceGcCursor.objects.select_for_update().get(pk=1)
            versions = (
                ResourceVersion.objects.filter(
                    state__in=["ready", "retired"],
                    metadata_holders__isnull=True,
                    video_holders__isnull=True,
                    pool__retained=False,
                )
                .filter(Q(gc_after__lte=now) | Q(gc_after__isnull=True))
                .order_by("pk")
            )
            pools = ResourcePoolEntry.objects.filter(
                state="pending_gc",
                gc_after__lte=now,
                retained=False,
                memberships__isnull=True,
            ).order_by("pk")
            selected_versions = (
                list(
                    versions.filter(pk__gt=cursor.version_after).values(
                        "pool_id", "pk"
                    )[:limit]
                )
                if cursor.version_after
                else list(versions.values("pool_id", "pk")[:limit])
            )
            selected_pools = (
                list(
                    pools.filter(pk__gt=cursor.pool_after).values_list("pk", flat=True)[
                        :limit
                    ]
                )
                if cursor.pool_after
                else list(pools.values_list("pk", flat=True)[:limit])
            )
            if not selected_versions:
                selected_versions = list(versions.values("pool_id", "pk")[:limit])
            if not selected_pools:
                selected_pools = list(pools.values_list("pk", flat=True)[:limit])
            cursor.version_after = (
                selected_versions[-1]["pk"] if selected_versions else None
            )
            cursor.pool_after = selected_pools[-1] if selected_pools else None
            cursor.save(update_fields=["version_after", "pool_after"])
        return selected_versions, selected_pools
