"""Short DB fences, snapshots and bounded session recovery."""

from datetime import timedelta
from uuid import uuid4
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone
from django.utils.crypto import salted_hmac
from nassav.models import AVResource
from .contracts import PlaybackStopped, PreparationToken
from .models import PlaybackSession

IDLE_SECONDS = 1800
MAX_SECONDS = 14400


def login_hash(key):
    if not key:
        raise PlaybackStopped("Missing login session")
    return salted_hmac("nassav-playback-login", key).hexdigest()


def snapshot(row):
    return {
        "session_id": str(row.pk),
        "state": row.state,
        "version": row.version,
        "generation": row.generation,
        "error_code": row.error_code,
        "allowed_actions": (["close"] if row.state not in {"closed", "failed"} else [])
        + (
            ["refresh"]
            if row.state == "ready"
            and row.refresh_count == 0
            and row.manifest_identity
            and all(v.get("digest") for v in row.manifest_identity.values())
            else []
        ),
        "refresh_count": row.refresh_count,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
        "expires_at": min(row.idle_expires_at, row.absolute_expires_at).isoformat(),
    }


def submit(user_id, key, avid, request_id):
    now = timezone.now()
    binding = login_hash(key)
    with transaction.atomic():
        # Serializes the per-user capacity check on both SQLite and PostgreSQL.
        get_user_model().objects.filter(pk=user_id).update(last_login=F("last_login"))
        previous = PlaybackSession.objects.filter(
            user_id=user_id, login_hash=binding, request_id=request_id
        ).first()
        if previous:
            if previous.resource.avid != avid:
                raise ValueError("Request identity conflict")
            return previous
        resource = AVResource.objects.get(avid=avid)
        if (
            PlaybackSession.objects.filter(
                user_id=user_id,
                state__in=["queued", "resolving", "ready"],
                idle_expires_at__gt=now,
                absolute_expires_at__gt=now,
            ).count()
            >= 2
        ):
            raise PlaybackStopped("Playback capacity reached")
        return PlaybackSession.objects.create(
            user_id=user_id,
            login_hash=binding,
            resource=resource,
            source=resource.source.lower(),
            request_id=request_id,
            prepare_deadline=now + timedelta(seconds=300),
            dispatch_after=now,
            last_seen_at=now,
            idle_expires_at=now + timedelta(seconds=IDLE_SECONDS),
            absolute_expires_at=now + timedelta(seconds=MAX_SECONDS),
        )


def owned(session_id, user_id, key):
    row = PlaybackSession.objects.filter(
        pk=session_id, user_id=user_id, login_hash=login_hash(key)
    ).first()
    if row is None:
        raise PlaybackSession.DoesNotExist
    return row


def close(session_id, user_id, key, expected_version, request_id):
    with transaction.atomic():
        row = owned(session_id, user_id, key)
        if row.last_command_id == request_id and row.state == "closed":
            return row
        if row.version != expected_version:
            raise PlaybackStopped("Version conflict")
        if not PlaybackSession.objects.filter(
            pk=row.pk, version=expected_version
        ).update(
            state="closed",
            version=F("version") + 1,
            generation=F("generation") + 1,
            descriptor={},
            lease_until=None,
            updated_at=timezone.now(),
            last_command_id=request_id,
        ):
            raise PlaybackStopped("Version conflict")
        return owned(session_id, user_id, key)


def claim(session_id):
    now = timezone.now()
    if not PlaybackSession.objects.filter(
        pk=session_id,
        state="queued",
        prepare_deadline__gt=now,
        idle_expires_at__gt=now,
        absolute_expires_at__gt=now,
    ).update(
        state="resolving",
        version=F("version") + 1,
        lease_until=now + timedelta(seconds=90),
        updated_at=now,
    ):
        return None
    row = PlaybackSession.objects.get(pk=session_id)
    return PreparationToken(row.pk, row.execution_id, row.generation)


def execution_rows(token):
    now = timezone.now()
    return PlaybackSession.objects.filter(
        pk=token.session_id,
        execution_id=token.execution_id,
        generation=token.generation,
        state="resolving",
        lease_until__gt=now,
        prepare_deadline__gt=now,
        idle_expires_at__gt=now,
        absolute_expires_at__gt=now,
    )


def check(token):
    if not execution_rows(token).update(
        lease_until=timezone.now() + timedelta(seconds=90)
    ):
        raise PlaybackStopped("Playback preparation no longer owned")


def publish(token, operation):
    with transaction.atomic():
        if not execution_rows(token).update(version=F("version")):
            raise PlaybackStopped("Playback preparation no longer owned")
        return operation()


def ready(token, descriptor):
    descriptor.validate()
    from dataclasses import asdict

    def commit():
        if not execution_rows(token).update(
            state="ready",
            descriptor=asdict(descriptor),
            lease_until=None,
            version=F("version") + 1,
            updated_at=timezone.now(),
        ):
            raise PlaybackStopped("Playback preparation no longer owned")

    publish(token, commit)


def fail(token, code="preparation_failed"):
    execution_rows(token).update(
        state="failed",
        error_code=code,
        descriptor={},
        lease_until=None,
        version=F("version") + 1,
        updated_at=timezone.now(),
    )


def recover(dispatch, limit=100):
    now = timezone.now()
    expired = (
        Q(prepare_deadline__lte=now, state__in=["queued", "resolving"])
        | Q(state="resolving", lease_until__lte=now)
        | Q(idle_expires_at__lte=now)
        | Q(absolute_expires_at__lte=now)
    )
    ids = list(
        PlaybackSession.objects.filter(expired)
        .exclude(state__in=["failed", "closed"])
        .values_list("pk", flat=True)[:limit]
    )
    PlaybackSession.objects.filter(pk__in=ids).filter(expired).update(
        state="failed",
        error_code="expired",
        descriptor={},
        lease_until=None,
        version=F("version") + 1,
        updated_at=now,
    )
    for session_id in list(
        PlaybackSession.objects.filter(
            state="queued", dispatch_after__lte=now, prepare_deadline__gt=now
        ).values_list("pk", flat=True)[:limit]
    ):
        if PlaybackSession.objects.filter(
            pk=session_id, state="queued", dispatch_after__lte=now
        ).update(dispatch_after=now + timedelta(seconds=30)):
            try:
                dispatch(str(session_id))
            except Exception:
                # Durable queued state remains eligible for the next bounded retry.
                pass
    stale = list(
        PlaybackSession.objects.filter(
            state__in=["closed", "failed"], updated_at__lt=now - timedelta(days=1)
        ).values_list("pk", flat=True)[:limit]
    )
    PlaybackSession.objects.filter(
        pk__in=stale,
        state__in=["closed", "failed"],
        updated_at__lt=now - timedelta(days=1),
    ).delete()


def close_login(key):
    if key:
        PlaybackSession.objects.filter(login_hash=login_hash(key)).exclude(
            state="closed"
        ).update(
            state="closed",
            descriptor={},
            lease_until=None,
            generation=F("generation") + 1,
            version=F("version") + 1,
            updated_at=timezone.now(),
        )


def preparation_input(token):
    row = execution_rows(token).select_related("resource").first()
    if row is None:
        raise PlaybackStopped("Playback preparation no longer owned")
    return (
        row.resource.avid,
        row.source,
        (row.prepare_deadline - timezone.now()).total_seconds(),
    )


def refresh(session_id, user_id, key, expected_version, request_id):
    now = timezone.now()
    with transaction.atomic():
        row = owned(session_id, user_id, key)
        if row.last_command_id == request_id and row.refresh_count == 1:
            return row
        if (
            row.version != expected_version
            or row.state != "ready"
            or row.refresh_count != 0
            or not row.manifest_identity
            or not all(v.get("digest") for v in row.manifest_identity.values())
            or min(row.idle_expires_at, row.absolute_expires_at) <= now
        ):
            raise PlaybackStopped("Refresh unavailable")
        if not PlaybackSession.objects.filter(
            pk=row.pk,
            version=expected_version,
            state="ready",
            refresh_count=0,
            idle_expires_at__gt=now,
            absolute_expires_at__gt=now,
        ).update(
            state="queued",
            refresh_count=1,
            generation=F("generation") + 1,
            execution_id=uuid4(),
            descriptor={},
            lease_until=None,
            prepare_deadline=min(now + timedelta(seconds=300), row.absolute_expires_at),
            dispatch_after=now,
            version=F("version") + 1,
            updated_at=now,
            last_command_id=request_id,
            error_code="",
        ):
            raise PlaybackStopped("Refresh unavailable")
        return owned(session_id, user_id, key)


def refresh_context(token):
    row = execution_rows(token).first()
    if row is None:
        raise PlaybackStopped("Playback preparation no longer owned")
    return row.refresh_count > 0, row.manifest_identity


def observe_identity(session_id, generation, path, kind, digest, dependencies=()):
    """Persist only bounded hashes; the short fence rejects stale media observers."""
    from .policy import PlaybackGatewayError

    now = timezone.now()
    with transaction.atomic():
        rows = PlaybackSession.objects.filter(
            pk=session_id,
            generation=generation,
            state="ready",
            idle_expires_at__gt=now,
            absolute_expires_at__gt=now,
        )
        if not rows.update(version=F("version")):
            raise PlaybackGatewayError("session_closed", 410)
        row = rows.get()
        previous = row.manifest_identity.get(path)
        value = {"kind": kind, "digest": digest}
        if previous and previous.get("digest") and previous != value:
            raise PlaybackGatewayError("media_identity_changed", 422)
        if not previous or not previous.get("digest"):
            additions = {
                child: {"kind": child_kind, "digest": None}
                for child, child_kind in dependencies
                if child not in row.manifest_identity
            }
            if (
                len(row.manifest_identity) + len(additions) + (0 if previous else 1)
                > 128
            ):
                raise PlaybackGatewayError("identity_limit_exceeded", 422)
            row.manifest_identity.update(additions)
            row.manifest_identity[path] = value
            rows.update(
                manifest_identity=row.manifest_identity,
                version=F("version") + 1,
                updated_at=now,
            )
