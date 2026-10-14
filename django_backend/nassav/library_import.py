"""Explicit, read-only-by-default legacy ownership import, with no media I/O."""

from django.contrib.auth import get_user_model
from django.db import transaction

from nassav.db_retry import retry_sqlite_contention
from nassav.library_models import ResourcePoolEntry, UserLibraryEntry
from nassav.models import AVResource
from nassav.personal_state import lock_user
from nassav.task_control_rules import normalize_avid


class LibraryImportConflict(ValueError):
    pass


def _resources():
    rows = list(AVResource.objects.values("pk", "avid", "source"))
    identities = set()
    for row in rows:
        identity = normalize_avid(row["avid"])
        if identity in identities:
            raise LibraryImportConflict(f"资源规范身份冲突: {identity}")
        identities.add(identity)
        row["identity"] = identity
    return sorted(rows, key=lambda row: row["identity"])


def _validate_pool(pool, resource):
    if (
        not pool.is_available
        or pool.state in {"deleting", "cleanup_failed", "reclaimed"}
        or pool.resource_id != resource["pk"]
    ):
        raise LibraryImportConflict(f"池身份或生命周期冲突: {resource['identity']}")


@retry_sqlite_contention
def import_legacy_library(username, *, apply=False):
    user = get_user_model().objects.get(
        **{getattr(get_user_model(), "USERNAME_FIELD", "username"): username},
        is_active=True,
    )
    if not apply:
        resources = _resources()
        pools = {
            row.canonical_avid: row
            for row in ResourcePoolEntry.objects.filter(
                canonical_avid__in=[r["identity"] for r in resources]
            )
        }
        for row in resources:
            if row["identity"] in pools:
                _validate_pool(pools[row["identity"]], row)
        return {
            "username": username,
            "resource_count": len(resources),
            "applied": False,
        }
    with transaction.atomic():
        lock_user(user.pk)
        resources = _resources()
        new_pools = new_memberships = 0
        for row in resources:
            pool, created = ResourcePoolEntry.objects.get_or_create(
                canonical_avid=row["identity"],
                defaults={"resource_id": row["pk"], "state": "ready"},
            )
            pool = ResourcePoolEntry.objects.select_for_update().get(pk=pool.pk)
            _validate_pool(pool, row)
            # Preserve edited/pending relationships; importing is not a refresh.
            entry, new = UserLibraryEntry.objects.get_or_create(
                user=user,
                pool=pool,
                defaults={
                    "state": "active",
                    "desired_spec": {
                        "source": row["source"].strip().lower() or "legacy"
                    },
                    "access_scope": f"legacy:operator:{user.pk}",
                },
            )
            if new and pool.state == "pending_gc":
                pool.state = "ready"
                pool.gc_after = None
                pool.lifetime_generation += 1
                pool.version += 1
                pool.save(
                    update_fields=[
                        "state",
                        "gc_after",
                        "lifetime_generation",
                        "version",
                        "updated_at",
                    ]
                )
            new_pools += int(created)
            new_memberships += int(new)
        return {
            "username": username,
            "resource_count": len(resources),
            "applied": True,
            "new_pools": new_pools,
            "new_memberships": new_memberships,
        }
