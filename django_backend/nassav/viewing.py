"""Personal queues; recording playback never acquires progress-writing ownership."""

from django.db import transaction
from django.db.models import F
from django.db.models.functions import Coalesce
from django.utils import timezone
from nassav.db_retry import retry_sqlite_contention
from nassav.personal_state import lock_user, project_personal_state
from nassav.personal_models import UserWatchHistory, UserResourceState
from nassav.library_models import ResourcePoolEntry
from nassav.playback import records, progress
from nassav.playback.policy import PlaybackGatewayError


@retry_sqlite_contention
def record_view(session_id, user_id, login_key, generation, sequence):
    if type(generation) is not int or generation < 1:
        raise ValueError("Invalid generation")
    if type(sequence) is not int or not 1 <= sequence <= 2147483647:
        raise ValueError("Invalid sequence")
    with transaction.atomic():
        lock_user(user_id)
        candidate = records.owned(session_id, user_id, login_key)
        pool, _ = ResourcePoolEntry.objects.get_or_create(
            canonical_avid=candidate.resource.avid.strip().upper(),
            defaults={"resource": candidate.resource, "state": "ready"},
        )
        pool = ResourcePoolEntry.objects.select_for_update().get(pk=pool.pk)
        session = records.owned_for_update(session_id, user_id, login_key)
        progress.active(session)
        from django.contrib.auth import get_user_model
        from nassav.account_policy import can_read_playback

        if not can_read_playback(get_user_model().objects.get(pk=user_id), session):
            raise PlaybackGatewayError("resource_not_available", 404)
        if session.generation != generation:
            raise PlaybackGatewayError("stale_generation", 409)
        # Monotonic episode sequences fence retries; a genuine resume can move
        # the entry to the front, but old requests cannot reorder it.
        if sequence > session.history_sequence:
            now = timezone.now()
            UserWatchHistory.objects.update_or_create(
                user_id=user_id,
                pool=pool,
                defaults={
                    "resource_id": session.resource.pk,
                    "snapshot": viewing_snapshot(session, pool),
                    "last_watched_at": now,
                    "media_kind": session.media_kind,
                },
            )
            session.history_sequence = sequence
            session.history_recorded_at = now
            session.save(update_fields=["history_recorded_at", "history_sequence"])
        return {
            "avid": session.resource.avid,
            "recorded_at": session.history_recorded_at.isoformat(),
        }


def viewing_snapshot(session, pool):
    from nassav.resource_version_models import ResourceVersion

    version_id = session.library_grant.get("version_id")
    if version_id:
        version = ResourceVersion.objects.get(pk=version_id, pool=pool)
        fields = version.metadata
        source = version.source_name
    else:
        resource = session.resource
        fields = {
            key: getattr(resource, key)
            for key in ("original_title", "source_title", "translated_title")
        }
        source = resource.source
    return {
        "avid": pool.canonical_avid,
        **{
            key: fields.get(key, "") or ""
            for key in ("original_title", "source_title", "translated_title")
        },
        "source": source,
    }


def list_viewing(user_id, kind, page, page_size):
    from nassav.models import AVResource
    from nassav.serializers import ResourceSummarySerializer
    from nassav.library_catalog import enabled, held_entries, project

    scoped = enabled(user_id)
    from nassav.account_models import UserAccount
    from nassav.account_policy import own_resource_ids

    managed = scoped or UserAccount.objects.filter(user_id=user_id).exists()
    if kind == "history":
        rows = (
            UserWatchHistory.objects.filter(user_id=user_id)
            .annotate(queue_time=F("last_watched_at"))
            .order_by("-last_watched_at", "-pk")
        )
        fields = ("resource_id", "queue_time", "snapshot", "pool__canonical_avid")
    elif kind == "watch-later":
        rows = UserResourceState.objects.filter(user_id=user_id, watch_later=True)
        if scoped:
            rows = rows.filter(
                resource_id__in=held_entries(user_id).values("pool__resource_id")
            )
        elif managed:
            rows = rows.filter(resource_id__in=own_resource_ids(user_id))
        rows = rows.annotate(
            queue_time=Coalesce("watch_later_added_at", "updated_at")
        ).order_by("-watch_later_added_at", "-pk")
        fields = ("resource_id", "queue_time")
    else:
        raise ValueError("Invalid collection")
    total = rows.count()
    pages = max(1, (total + page_size - 1) // page_size)
    page = min(page, pages)
    selected = list(rows[(page - 1) * page_size : page * page_size].values(*fields))
    ids = [row["resource_id"] for row in selected if row["resource_id"] is not None]
    if scoped:
        entries = project_personal_state(
            held_entries(user_id).filter(pool__resource_id__in=ids),
            user_id,
            resource_field="pool__resource_id",
        )
        by_id = {entry.pool.resource_id: project(entry) for entry in entries}
    else:
        resources = AVResource.objects.filter(pk__in=ids).prefetch_related("genres")
        if managed:
            resources = resources.filter(pk__in=own_resource_ids(user_id))
        resources = project_personal_state(resources, user_id)
        by_id = {row.pk: dict(ResourceSummarySerializer(row).data) for row in resources}
    data = []
    for row in selected:
        current = by_id.get(row["resource_id"])
        if kind == "watch-later" and current is None:
            continue
        item = dict(
            current
            or {
                "avid": row.get("pool__canonical_avid", ""),
                "thumbnail_url": None,
                "has_video": False,
                "file_exists": False,
                "watched": False,
                "is_favorite": False,
                "watch_later": False,
                "actors": [],
                "genres": [],
            }
        )
        if kind == "history":
            # This user's own historical display facts grant no file/media access.
            snapshot = row["snapshot"]
            for key in ("original_title", "source_title", "translated_title", "source"):
                item[key] = snapshot.get(key, "")
            item["avid"] = row["pool__canonical_avid"]
        item["is_available"] = current is not None
        item["queue_time"] = row["queue_time"].isoformat()
        data.append(item)
    return data, {"page": page, "pages": pages, "page_size": page_size, "total": total}


@retry_sqlite_contention
def remove_watched_later(user_id):
    """Only explicit watched markers qualify; retain all other personal fields."""
    with transaction.atomic():
        lock_user(user_id)
        return UserResourceState.objects.filter(
            user_id=user_id, watch_later=True, watched=True
        ).update(
            watch_later=False,
            watch_later_added_at=None,
            version=F("version") + 1,
            updated_at=timezone.now(),
        )


@retry_sqlite_contention
def remove_history(user_id, entries):
    from django.utils.dateparse import parse_datetime

    if not isinstance(entries, list) or not 1 <= len(entries) <= 200:
        raise ValueError("请选择1至200条历史记录")
    validated = []
    seen = set()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"avid", "queue_time"}:
            raise ValueError("历史记录参数无效")
        avid, stamp = entry["avid"], entry["queue_time"]
        if (
            not isinstance(avid, str)
            or not avid
            or avid in seen
            or not isinstance(stamp, str)
        ):
            raise ValueError("历史记录参数无效")
        stamp = parse_datetime(stamp)
        if stamp is None or timezone.is_naive(stamp):
            raise ValueError("历史记录时间无效")
        seen.add(avid)
        validated.append((avid, stamp))
    results = []
    with transaction.atomic():
        lock_user(user_id)
        rows = {
            row["pool__canonical_avid"]: row
            for row in UserWatchHistory.objects.filter(
                user_id=user_id, pool__canonical_avid__in=seen
            ).values("pk", "pool__canonical_avid", "last_watched_at")
        }
        deleted = []
        for avid, stamp in validated:
            row = rows.get(avid)
            if row is None:
                status = "absent"
            elif row["last_watched_at"] != stamp:
                status = "conflict"
            else:
                status = "removed"
                deleted.append(row["pk"])
            results.append({"avid": avid, "status": status})
        UserWatchHistory.objects.filter(user_id=user_id, pk__in=deleted).delete()
    return results
