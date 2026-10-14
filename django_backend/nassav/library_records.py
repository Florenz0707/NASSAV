"""Short user -> pool -> membership writes on SQLite and PostgreSQL."""

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from nassav.db_retry import retry_sqlite_contention
from nassav.library_membership import LibraryConflict, LibraryNotFound
from nassav.library_models import ResourcePoolEntry, UserLibraryEntry
from nassav.personal_models import UserResourceState
from nassav.personal_state import lock_user


def membership_snapshot(entry, pool):
    return {
        "entry_id": str(entry.pk),
        "entry_version": entry.version,
        "pool_id": str(pool.pk),
        "pool_generation": pool.lifetime_generation,
        "avid": pool.canonical_avid,
        "membership_state": entry.state,
        "is_in_my_library": True,
    }


class DjangoMembershipRecords:
    @retry_sqlite_contention
    def attach(self, user_id, avid, source, scope):
        with transaction.atomic():
            lock_user(user_id)
            # get_or_create isolates a raced insert in a savepoint on PostgreSQL.
            pool, _ = ResourcePoolEntry.objects.get_or_create(canonical_avid=avid)
            pool = ResourcePoolEntry.objects.select_for_update().get(pk=pool.pk)
            if pool.state in {"deleting", "cleanup_failed"}:
                raise LibraryConflict("resource_reclaiming")
            existing = UserLibraryEntry.objects.filter(
                user_id=user_id, pool=pool
            ).first()
            desired = {"source": source}
            if existing:
                if existing.desired_spec != desired or existing.access_scope != scope:
                    raise LibraryConflict(
                        "membership_spec_conflict", membership_snapshot(existing, pool)
                    )
                return membership_snapshot(existing, pool)
            if pool.state in {"pending_gc", "reclaimed"}:
                pool.lifetime_generation += 1
                pool.version += 1
                pool.state = "ready" if pool.resource_id else "preparing"
                pool.gc_after = None
                pool.save(
                    update_fields=[
                        "lifetime_generation",
                        "version",
                        "state",
                        "gc_after",
                        "updated_at",
                    ]
                )
            entry = UserLibraryEntry.objects.create(
                user_id=user_id,
                pool=pool,
                desired_spec=desired,
                access_scope=scope,
            )
            return membership_snapshot(entry, pool)

    @retry_sqlite_contention
    def release(self, user_id, entry_id, expected_version, grace):
        with transaction.atomic():
            lock_user(user_id)
            entry = UserLibraryEntry.objects.filter(
                pk=entry_id, user_id=user_id
            ).first()
            if entry is None:
                raise LibraryNotFound("Membership not found")
            pool = ResourcePoolEntry.objects.select_for_update().get(pk=entry.pool_id)
            # User fence prevents own release/attach from replacing this row.
            if entry.version != expected_version:
                raise LibraryConflict(
                    "version_conflict", membership_snapshot(entry, pool)
                )
            if pool.resource_id:
                UserResourceState.objects.filter(
                    user_id=user_id, resource_id=pool.resource_id, watch_later=True
                ).update(
                    watch_later=False,
                    watch_later_added_at=None,
                    version=F("version") + 1,
                    updated_at=timezone.now(),
                )
            entry.delete()
            if not pool.memberships.exists() and pool.state not in {
                "deleting",
                "cleanup_failed",
            }:
                pool.state = "pending_gc"
                pool.gc_after = timezone.now() + grace
                pool.version += 1
                pool.save(update_fields=["state", "gc_after", "version", "updated_at"])
            return {
                "released": True,
                "entry_id": str(entry_id),
                "entry_version": expected_version + 1,
                "gc_scheduled": pool.state == "pending_gc",
            }
