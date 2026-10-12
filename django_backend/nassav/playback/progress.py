"""Personal progress with short database writer fences; no media/network work."""

import hashlib
import json
import math
from uuid import UUID
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from nassav.db_retry import retry_sqlite_contention
from . import records
from .models import PlaybackProgress
from .policy import PlaybackGatewayError


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def media_key(session):
    if session.media_kind == "local":
        identity = session.descriptor
    else:
        # A source ledger identifies a resource/provider, NOT proven media bytes.
        identity = {"avid": session.resource.avid, "source": session.source}
    return digest([session.media_kind, identity])


def snapshot(row, session):
    return {
        "ledger_key": digest(
            [session.user_id, session.resource.avid, media_key(session)]
        ),
        "position_seconds": row.position_seconds if row else 0,
        "duration_seconds": row.duration_seconds if row else 0,
        "completed": row.completed if row else False,
        "version": row.version if row else 0,
        "writer_generation": row.writer_generation if row else 0,
        "restore_policy": "confirm" if session.media_kind == "source" else "exact",
        "updated_at": row.updated_at.isoformat() if row else None,
    }


def active(session):
    if (
        session.state != "ready"
        or min(session.idle_expires_at, session.absolute_expires_at) <= timezone.now()
    ):
        raise PlaybackGatewayError("session_closed", 410)


def query(session):
    active(session)
    row = PlaybackProgress.objects.filter(
        user_id=session.user_id,
        avid=session.resource.avid,
        media_key=media_key(session),
    ).first()
    return snapshot(row, session)


@retry_sqlite_contention
def claim(session_id, user_id, key, generation, command, expected_writer_generation):
    with transaction.atomic():
        get_user_model().objects.filter(pk=user_id).update(last_login=F("last_login"))
        session = records.owned_for_update(session_id, user_id, key)
        active(session)
        if session.generation != generation:
            raise PlaybackGatewayError("progress_writer_conflict", 409)
        row, _ = PlaybackProgress.objects.get_or_create(
            user_id=user_id,
            avid=session.resource.avid,
            media_key=media_key(session),
            defaults={"media_kind": session.media_kind, "source": session.source},
        )
        if row.claim_id == command and row.writer_session == session.pk:
            return snapshot(row, session)
        if row.writer_generation != expected_writer_generation:
            raise PlaybackGatewayError("progress_writer_conflict", 409)
        row.writer_generation += 1
        row.writer_session = session.pk
        row.claim_id = command
        row.last_sequence = 0
        row.last_payload = ""
        row.save()
        return snapshot(row, session)


@retry_sqlite_contention
def save(session_id, user_id, key, payload):
    required = (
        "session_generation",
        "writer_generation",
        "sequence",
        "expected_version",
    )
    if any(
        type(payload.get(name)) is not int or payload[name] < 1 for name in required
    ):
        raise ValueError("Invalid progress token")
    position, duration = (
        payload.get("position_seconds"),
        payload.get("duration_seconds"),
    )
    if (
        any(
            type(v) not in (int, float) or not math.isfinite(v)
            for v in (position, duration)
        )
        or not 0 <= position <= duration <= 604800
        or duration == 0
    ):
        raise ValueError("Invalid progress position")
    if type(payload.get("completed")) is not bool:
        raise ValueError("Invalid completion")
    UUID(str(payload.get("request_id")))
    body_hash = digest(payload)
    with transaction.atomic():
        get_user_model().objects.filter(pk=user_id).update(last_login=F("last_login"))
        session = records.owned_for_update(session_id, user_id, key)
        active(session)
        row = PlaybackProgress.objects.filter(
            user_id=user_id, avid=session.resource.avid, media_key=media_key(session)
        ).first()
        if (
            not row
            or session.generation != payload["session_generation"]
            or row.writer_session != session.pk
            or row.writer_generation != payload["writer_generation"]
        ):
            raise PlaybackGatewayError("progress_writer_conflict", 409)
        if row.last_sequence == payload["sequence"] and row.last_payload == body_hash:
            return snapshot(row, session)
        if (
            row.version != payload["expected_version"]
            or payload["sequence"] <= row.last_sequence
        ):
            raise PlaybackGatewayError("progress_version_conflict", 409)
        row.position_seconds, row.duration_seconds = position, duration
        row.completed = payload["completed"]
        row.version += 1
        row.last_sequence = payload["sequence"]
        row.last_payload = body_hash
        row.save()
        return snapshot(row, session)


@retry_sqlite_contention
def clear(user_id, avid):
    # Tombstones revoke old writers; deleting rows would permit token reuse.
    with transaction.atomic():
        get_user_model().objects.filter(pk=user_id).update(last_login=F("last_login"))
        PlaybackProgress.objects.filter(user_id=user_id, avid=avid).update(
            position_seconds=0,
            duration_seconds=0,
            completed=False,
            writer_session=None,
            claim_id=None,
            writer_generation=F("writer_generation") + 1,
            version=F("version") + 1,
            last_sequence=0,
            last_payload="",
            updated_at=timezone.now(),
        )
