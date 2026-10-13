"""Resource response shapes shared by synchronous and job entrypoints."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nassav.models import AVResource


def serialize_resource(resource: AVResource, include_relations: bool = False) -> dict:
    """
    序列化资源对象

    Args:
        resource: AVResource对象
        include_relations: 是否包含关系字段（actors, genres）

    Returns:
        资源字典
    """
    data = {
        "avid": resource.avid,
        "original_title": resource.original_title,
        "source_title": resource.source_title,
        "translated_title": resource.translated_title,
        "translation_status": resource.translation_status,
        "source": resource.source,
        "release_date": resource.release_date,
        "duration": resource.duration,
        "m3u8": resource.m3u8,
        "cover_filename": resource.cover_filename,
        "file_exists": resource.file_exists,
        "file_size": resource.file_size,
        "metadata_created_at": (
            resource.metadata_created_at.isoformat()
            if resource.metadata_created_at
            else None
        ),
        "metadata_updated_at": (
            resource.metadata_updated_at.isoformat()
            if resource.metadata_updated_at
            else None
        ),
        "video_saved_at": (
            resource.video_saved_at.isoformat() if resource.video_saved_at else None
        ),
        "created_at": (
            resource.created_at.isoformat() if resource.created_at else None
        ),
    }

    if include_relations:
        data["actors"] = [actor.name for actor in resource.actors.all()]
        data["genres"] = [genre.name for genre in resource.genres.all()]

    return data


def serialize_legacy_resource(resource, *, user_id=None):
    """Convert AVResource instance to plain dict suitable for API responses."""
    try:
        actors = [a.name for a in resource.actors.all()]
    except Exception:
        actors = []
    try:
        genres = [g.name for g in resource.genres.all()]
    except Exception:
        genres = []

    data = {
        "avid": resource.avid,
        "original_title": resource.original_title or "",
        "source_title": resource.source_title or "",
        "translated_title": resource.translated_title or "",
        "m3u8": resource.m3u8 or "",
        "source": resource.source or "",
        "release_date": resource.release_date or "",
        "duration": resource.duration,
        "actors": actors,
        "genres": genres,
        "file_size": resource.file_size,
        "file_exists": bool(resource.file_exists),
        "watched": False,
        "is_favorite": False,
    }

    if user_id is not None:
        from nassav.personal_state import state_snapshot

        data.update(state_snapshot(resource, user_id))
    return data
