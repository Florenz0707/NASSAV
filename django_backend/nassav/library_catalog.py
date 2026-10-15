"""Owned version projection, never a public copy of private source facts."""

from django.conf import settings
from django.core.paginator import Paginator
from django.db.models import F, Q

from nassav.account_models import UserAccount
from nassav.library_models import UserLibraryEntry, ResourcePoolEntry
from nassav.library_membership import LibraryNotFound
from nassav.personal_state import project_personal_state
from nassav.resource_version_snapshot import validated_snapshot


def enabled(user_id):
    return (
        settings.SHARED_LIBRARY_ENABLED
        and UserAccount.objects.filter(user_id=user_id).exists()
    )


def version_filter(field, user_id, kind):
    return Q(
        **{
            f"{field}__pool_id": F("pool_id"),
            f"{field}__kind": kind,
            f"{field}__state__in": ["ready", "retired"],
            f"{field}__published_at__isnull": False,
        }
    ) & (
        Q(**{f"{field}__owner_id": user_id})
        | Q(**{f"{field}__owner__isnull": True, f"{field}__access_scope": "public"})
    )


def held_entries(user_id, *, include_pending=False):
    legacy = Q(
        current_version__isnull=True,
        access_scope__in=["public", f"legacy:operator:{user_id}"],
    )
    readable = Q(state="active") & (
        version_filter("current_version", user_id, "metadata") | legacy
    )
    if include_pending:
        readable |= Q(state="pending")
    return (
        UserLibraryEntry.objects.filter(
            user_id=user_id,
            user__is_active=True,
            pool__is_available=True,
            pool__state__in=["ready", "preparing"],
        )
        .filter(readable)
        .select_related("pool__resource", "current_version", "video_version")
        .prefetch_related("pool__resource__actors", "pool__resource__genres")
    )


def video_filter(user_id):
    return version_filter("video_version", user_id, "video") | Q(
        video_version__isnull=True,
        access_scope__in=["public", f"legacy:operator:{user_id}"],
        pool__resource__file_exists=True,
    )


def _video(entry):
    version = entry.video_version
    if version is not None:
        return bool(
            version.pool_id == entry.pool_id
            and version.kind == "video"
            and version.state in {"ready", "retired"}
            and version.published_at is not None
            and (
                version.owner_id == entry.user_id
                or (version.owner_id is None and version.access_scope == "public")
            )
        )
    return bool(
        entry.access_scope in {"public", f"legacy:operator:{entry.user_id}"}
        and entry.pool.resource is not None
        and entry.pool.resource.file_exists
    )


def metadata(entry):
    if entry.state != "active":
        return validated_snapshot(
            {"avid": entry.pool.canonical_avid}, entry.pool.canonical_avid
        )
    if entry.current_version is not None:
        return validated_snapshot(
            entry.current_version.metadata, entry.pool.canonical_avid
        )
    resource = entry.pool.resource
    if resource is None:
        raise LibraryNotFound("Resource not prepared")
    # Compatibility projection is a whitelist too; m3u8/raw HTML/headers stay private.
    return validated_snapshot(
        {
            "avid": resource.avid,
            "original_title": resource.original_title or "",
            "source_title": resource.source_title or "",
            "translated_title": resource.translated_title or "",
            "release_date": resource.release_date or "",
            "duration": resource.duration or 0,
            "translation_status": "completed"
            if resource.translation_status == "completed"
            else "not_requested",
            "actors": [row.name for row in resource.actors.all()],
            "genres": [row.name for row in resource.genres.all()],
        },
        resource.avid,
    )


def project(entry, *, detail=False):
    data = metadata(entry)
    version, resource = (
        entry.current_version if entry.state == "active" else None,
        entry.pool.resource,
    )
    has_video = entry.state == "active" and _video(entry)
    stamp = (
        version.published_at
        if version
        else (resource.metadata_updated_at if resource else None)
    )
    source = (
        version.source_name
        if version
        else (
            resource.source
            if resource and entry.state == "active"
            else entry.desired_spec.get("source", "")
        )
    )
    data.update(
        {
            "entry_id": str(entry.pk),
            "entry_version": entry.version,
            "membership_state": entry.state,
            "is_in_my_library": True,
            "version_id": str(version.pk) if version else None,
            "video_version_id": str(entry.video_version.pk)
            if has_video and entry.video_version
            else None,
            "source": source,
            "has_video": has_video,
            "file_exists": has_video,
            "file_size": (
                entry.video_version.file_size
                if entry.video_version
                else resource.file_size
                if resource
                else None
            )
            if has_video
            else None,
            "watched": getattr(entry, "personal_watched", False),
            "is_favorite": getattr(entry, "personal_is_favorite", False),
            "watch_later": getattr(entry, "personal_watch_later", False),
            "state_version": getattr(entry, "personal_state_version", 0),
            "metadata_create_time": entry.created_at.timestamp(),
            "metadata_update_time": stamp.timestamp() if stamp else None,
            "video_create_time": (
                entry.video_version.published_at.timestamp()
                if entry.video_version
                else resource.video_saved_at.timestamp()
                if resource and resource.video_saved_at
                else None
            )
            if has_video
            else None,
            "thumbnail_url": f"/nassav/api/resource/cover?avid={entry.pool.canonical_avid}&size=small"
            + (f"&v={version.pk}" if version else ""),
        }
    )
    if detail:
        data["notes"] = getattr(entry, "personal_notes", "")
        from nassav.version_image_files import asset_identity

        data["image_assets"] = (
            [
                {
                    "asset_id": asset_identity(asset),
                    "kind": asset["kind"],
                    "url": f"/nassav/api/library/entries/{entry.pk}/images/{asset_identity(asset)}",
                }
                for asset in version.manifest
                if isinstance(asset, dict)
                and asset.get("kind") in {"cover", "avatar"}
                and asset.get("root") == asset.get("kind")
                and isinstance(asset.get("path"), str)
            ]
            if version is not None
            else []
        )
    return data


def own_entry(user_id, *, entry_id=None, avid=None, include_pending=False):
    rows = held_entries(user_id, include_pending=include_pending)
    rows = project_personal_state(rows, user_id, resource_field="pool__resource_id")
    row = (
        rows.filter(pk=entry_id).first()
        if entry_id is not None
        else rows.filter(pool__canonical_avid=avid).first()
    )
    if row is None:
        raise LibraryNotFound("Object not available")
    return row


def lock_held_resource(user_id, resource):
    """Called after the user fence, before any personal mutation."""
    if enabled(user_id):
        pool = (
            ResourcePoolEntry.objects.select_for_update()
            .filter(resource=resource)
            .first()
        )
        if pool is None:
            raise LibraryNotFound("Object not available")
        own_entry(user_id, avid=pool.canonical_avid)


def list_entries(user_id, params, *, include_pending=False):
    rows = project_personal_state(
        held_entries(user_id, include_pending=include_pending),
        user_id,
        resource_field="pool__resource_id",
    )
    state = params.get("membership_state")
    if state:
        if state not in {"active", "pending"}:
            raise ValueError("Invalid membership state")
        rows = rows.filter(state=state)
    downloaded = params.get("file_exists")
    status = params.get("status")
    if status not in {None, "", "all", "downloaded", "pending"}:
        raise ValueError("Invalid resource status")
    if downloaded is not None or status in {"downloaded", "pending"}:
        wanted = (
            str(downloaded).lower() in {"1", "true", "yes"}
            if downloaded is not None
            else status == "downloaded"
        )
        condition = Q(state="active") & video_filter(user_id)
        rows = rows.filter(condition) if wanted else rows.exclude(condition)
    source = params.get("source")
    if source:
        names = [name.strip() for name in str(source).split(",") if name.strip()]
        rows = rows.filter(
            Q(state="active", current_version__source_name__in=names)
            | Q(
                state="active",
                current_version__isnull=True,
                pool__resource__source__in=names,
            )
            | Q(state="pending", desired_spec__source__in=names)
        )
    for key in ("watched", "is_favorite"):
        if params.get(key) is not None:
            rows = rows.filter(
                **{f"personal_{key}": str(params[key]).lower() in {"1", "true", "yes"}}
            )
    term = str(params.get("search", "")).strip()
    if term:
        condition = Q(pool__canonical_avid__icontains=term)
        for field in ("original_title", "source_title", "translated_title"):
            condition |= Q(
                state="active",
                **{f"current_version__metadata__{field}__icontains": term},
            )
            condition |= Q(
                state="active",
                current_version__isnull=True,
                **{f"pool__resource__{field}__icontains": term},
            )
        rows = rows.filter(condition)
    for param, relation in (("actor", "actors"), ("genre", "genres")):
        value = params.get(param)
        if value:
            if str(value).isdigit():
                from nassav.catalog_projection import own_term

                value = own_term(user_id, param, int(value)).name
            rows = rows.filter(
                Q(
                    state="active",
                    **{f"current_version__metadata__{relation}__icontains": str(value)},
                )
                | Q(
                    state="active",
                    current_version__isnull=True,
                    **{f"pool__resource__{relation}__name__icontains": str(value)},
                )
            ).distinct()
    ordering = params.get("ordering", "-created_at")
    allowed = {
        "avid": "pool__canonical_avid",
        "created_at": "created_at",
        "updated_at": "updated_at",
        "metadata_created_at": "created_at",
        "metadata_updated_at": "current_version__published_at",
        "video_saved_at": "video_version__published_at",
        "source": "current_version__source_name",
    }
    key = str(ordering).removeprefix("-")
    if key not in allowed:
        raise ValueError("Invalid resource ordering")
    if key == "video_saved_at":
        rows = rows.filter(state="active").filter(video_filter(user_id))
    rows = rows.order_by(
        ("-" if str(ordering).startswith("-") else "") + allowed[key], "-pk"
    )
    try:
        page, size = int(params.get("page", 1)), int(params.get("page_size", 20))
    except (TypeError, ValueError):
        raise ValueError("Invalid pagination") from None
    if page < 1 or not 1 <= size <= 100:
        raise ValueError("Invalid pagination")
    paginator = Paginator(rows, size)
    selected = paginator.get_page(page)
    return [project(row) for row in selected.object_list], {
        "total": paginator.count,
        "page": selected.number,
        "page_size": size,
        "pages": paginator.num_pages,
    }


def membership_statuses(user_id, avids):
    """One bounded owner query; absence never exposes global inventory."""
    if len(avids) > 100:
        raise ValueError("At most 100 resource identities")
    entries = {
        row["pool__canonical_avid"]: {
            "entry_id": str(row["pk"]),
            "entry_version": row["version"],
            "membership_state": row["state"],
            "is_in_my_library": True,
            "is_available": row["pool__is_available"]
            and row["pool__state"] in {"ready", "preparing"},
        }
        for row in UserLibraryEntry.objects.filter(
            user_id=user_id, pool__canonical_avid__in=avids
        ).values(
            "pk",
            "version",
            "state",
            "pool__canonical_avid",
            "pool__is_available",
            "pool__state",
        )
    }
    absent = {
        "entry_id": None,
        "entry_version": None,
        "membership_state": None,
        "is_in_my_library": False,
        "is_available": False,
    }
    return [{"avid": avid, **entries.get(avid, absent)} for avid in avids]
