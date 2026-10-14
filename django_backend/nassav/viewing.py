"""Personal queues; recording playback never acquires progress-writing ownership."""

from django.db import transaction
from django.db.models import F
from django.db.models.functions import Coalesce
from django.utils import timezone
from nassav.db_retry import retry_sqlite_contention
from nassav.personal_state import lock_user, project_personal_state
from nassav.personal_models import UserWatchHistory, UserResourceState
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
        session = records.owned_for_update(session_id, user_id, login_key)
        progress.active(session)
        if session.generation != generation:
            raise PlaybackGatewayError("stale_generation", 409)
        # Monotonic episode sequences fence retries; a genuine resume can move
        # the entry to the front, but old requests cannot reorder it.
        if sequence > session.history_sequence:
            now = timezone.now()
            UserWatchHistory.objects.update_or_create(
                user_id=user_id,
                resource_id=session.resource.pk,
                defaults={"last_watched_at": now, "media_kind": session.media_kind},
            )
            session.history_sequence = sequence
            session.history_recorded_at = now
            session.save(update_fields=["history_recorded_at", "history_sequence"])
        return {
            "avid": session.resource.avid,
            "recorded_at": session.history_recorded_at.isoformat(),
        }


def list_viewing(user_id, kind, page, page_size):
    from nassav.models import AVResource
    from nassav.serializers import ResourceSummarySerializer

    if kind == "history":
        rows = (
            UserWatchHistory.objects.filter(user_id=user_id)
            .annotate(queue_time=F("last_watched_at"))
            .order_by("-last_watched_at", "-pk")
        )
    elif kind == "watch-later":
        rows = (
            UserResourceState.objects.filter(user_id=user_id, watch_later=True)
            .annotate(queue_time=Coalesce("watch_later_added_at", "updated_at"))
            .order_by("-watch_later_added_at", "-pk")
        )
    else:
        raise ValueError("Invalid collection")
    total = rows.count()
    pages = max(1, (total + page_size - 1) // page_size)
    page = min(page, pages)
    selected = list(
        rows[(page - 1) * page_size : page * page_size].values(
            "resource_id", "queue_time"
        )
    )
    resources = project_personal_state(
        AVResource.objects.filter(
            pk__in=[row["resource_id"] for row in selected]
        ).prefetch_related("genres"),
        user_id,
    )
    by_id = {row.pk: row for row in resources}
    data = []
    for row in selected:
        resource = by_id.get(row["resource_id"])
        if resource is None:
            continue
        item = dict(ResourceSummarySerializer(resource).data)
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
            row["resource__avid"]: row
            for row in UserWatchHistory.objects.filter(
                user_id=user_id, resource__avid__in=seen
            ).values("pk", "resource__avid", "last_watched_at")
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
