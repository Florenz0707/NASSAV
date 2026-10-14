"""Bounded, user-owned continue-watching projection; no source/network work."""

from types import SimpleNamespace
from django.db.models import F, OuterRef, Subquery, Exists, Q
from nassav.models import AVResource
from .models import PlaybackProgress
from .progress import media_key


def list_continuations(user_id, *, limit, locator):
    latest = PlaybackProgress.objects.filter(
        user_id=user_id, avid=OuterRef("avid")
    ).order_by("-updated_at", "-pk")
    from nassav.account_models import UserAccount
    from nassav.account_policy import own_resource_ids

    resource_scope = (
        AVResource.objects.alias(
            managed_account=Exists(UserAccount.objects.filter(user_id=user_id))
        )
        .filter(Q(managed_account=False) | Q(pk__in=own_resource_ids(user_id)))
        .exclude(pool_entry__is_available=False)
    )
    exists = resource_scope.filter(avid=OuterRef("avid"))
    rows = list(
        PlaybackProgress.objects.filter(user_id=user_id)
        .annotate(
            latest_id=Subquery(latest.values("pk")[:1]),
            resource_exists=Exists(exists),
        )
        .filter(
            pk=F("latest_id"),
            resource_exists=True,
            completed=False,
            position_seconds__gt=5,
            duration_seconds__gt=5,
        )
        .order_by("-updated_at", "-pk")[: min(limit * 4, 96)]
    )
    resources = {
        item.avid: item
        for item in resource_scope.filter(avid__in=[row.avid for row in rows])
    }
    local = locator.identities({row.avid for row in rows if row.media_kind == "local"})
    from nassav.library_catalog import enabled, held_entries, metadata

    owned_metadata = {}
    if enabled(user_id):
        owned_metadata = {
            entry.pool.canonical_avid: {
                **metadata(entry),
                "source": entry.current_version.source_name
                if entry.current_version
                else entry.pool.resource.source,
                "_grant": {
                    "version_id": str(entry.current_version.pk),
                    "scope": entry.current_version.access_scope,
                    "context_revision": entry.current_version.context_revision,
                }
                if entry.current_version
                else {},
            }
            for entry in held_entries(user_id).filter(
                pool__canonical_avid__in=[row.avid for row in rows]
            )
        }
    result = []
    for row in rows:
        resource = resources.get(row.avid)
        if resource is None or row.position_seconds >= row.duration_seconds - 5:
            continue
        display = owned_metadata.get(row.avid)
        if row.media_kind == "local":
            identity = local.get(row.avid)
            if (
                not identity
                or media_key(SimpleNamespace(media_kind="local", descriptor=identity))
                != row.media_key
            ):
                continue
        elif (
            row.media_kind != "source"
            or row.source
            != str(display["source"] if display else resource.source or "").lower()
        ):
            continue
        elif (
            display
            and display["_grant"]
            and row.media_key
            != media_key(
                SimpleNamespace(
                    media_kind="source",
                    resource=resource,
                    source=display["source"],
                    library_grant=display["_grant"],
                )
            )
        ):
            continue
        result.append(
            {
                "avid": row.avid,
                "mode": row.media_kind,
                "original_title": display["original_title"]
                if display
                else resource.original_title,
                "source_title": display["source_title"]
                if display
                else resource.source_title,
                "translated_title": display["translated_title"]
                if display
                else resource.translated_title,
                "position_seconds": row.position_seconds,
                "duration_seconds": row.duration_seconds,
                "restore_policy": "exact" if row.media_kind == "local" else "confirm",
                "updated_at": row.updated_at.isoformat(),
            }
        )
        if len(result) == limit:
            break
    return result
