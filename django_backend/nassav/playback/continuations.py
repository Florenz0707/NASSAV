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
    result = []
    for row in rows:
        resource = resources.get(row.avid)
        if resource is None or row.position_seconds >= row.duration_seconds - 5:
            continue
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
            or row.source != str(resource.source or "").lower()
        ):
            continue
        result.append(
            {
                "avid": row.avid,
                "mode": row.media_kind,
                "original_title": resource.original_title,
                "source_title": resource.source_title,
                "translated_title": resource.translated_title,
                "position_seconds": row.position_seconds,
                "duration_seconds": row.duration_seconds,
                "restore_policy": "exact" if row.media_kind == "local" else "confirm",
                "updated_at": row.updated_at.isoformat(),
            }
        )
        if len(result) == limit:
            break
    return result
