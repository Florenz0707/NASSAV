"""Audited availability controls; downlisting closes readers and never deletes files."""

import json
from uuid import UUID
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from django.utils.crypto import salted_hmac
from nassav.account_management import AccountConflict, REASONS
from nassav.account_models import (
    AccountControl,
    UserAccount,
    AuditEvent,
    AdminCommandReceipt,
)
from nassav.library_models import ResourcePoolEntry
from nassav.playback.models import PlaybackSession
from nassav.db_retry import retry_sqlite_contention


@retry_sqlite_contention
def set_availability(actor_id, pool_id, command):
    if not isinstance(command, dict) or set(command) != {
        "request_id",
        "reason",
        "expected_version",
        "available",
    }:
        raise ValueError("Invalid availability command")
    if (
        not isinstance(command["reason"], str)
        or command["reason"] not in REASONS
        or type(command["available"]) is not bool
        or type(command["expected_version"]) is not int
        or command["expected_version"] < 1
    ):
        raise ValueError("Invalid availability parameters")
    request_id, pool_id = UUID(str(command["request_id"])), UUID(str(pool_id))
    digest = salted_hmac(
        "nassav-admin-command",
        json.dumps(["resource.availability", str(pool_id), command], sort_keys=True),
    ).hexdigest()
    with transaction.atomic():
        AccountControl.objects.get_or_create(pk=1)
        AccountControl.objects.filter(pk=1).update(version=F("version"))
        if (
            not get_user_model()
            .objects.filter(pk=actor_id, is_active=True)
            .update(last_login=F("last_login"))
            or not UserAccount.objects.filter(user_id=actor_id, role="admin").exists()
        ):
            raise PermissionError("Application admin required")
        prior = AdminCommandReceipt.objects.filter(
            actor_id=actor_id, request_id=request_id
        ).first()
        if prior:
            if prior.payload_hash != digest:
                raise AccountConflict("request_id_conflict")
            return prior.result
        pool = ResourcePoolEntry.objects.select_for_update().get(pk=pool_id)
        if pool.version != command["expected_version"]:
            raise AccountConflict("resource_version_conflict")
        if pool.state in {"deleting", "cleanup_failed", "reclaimed"}:
            raise AccountConflict("resource_reclaiming")
        pool.is_available = command["available"]
        pool.version += 1
        pool.save(update_fields=["is_available", "version", "updated_at"])
        if not pool.is_available and pool.resource_id:
            PlaybackSession.objects.filter(resource_id=pool.resource_id).exclude(
                state="closed"
            ).update(
                state="closed",
                descriptor={},
                lease_until=None,
                generation=F("generation") + 1,
                version=F("version") + 1,
                updated_at=timezone.now(),
            )
        result = {
            "pool_id": str(pool.pk),
            "available": pool.is_available,
            "version": pool.version,
        }
        AdminCommandReceipt.objects.create(
            actor_id=actor_id, request_id=request_id, payload_hash=digest, result=result
        )
        AuditEvent.objects.create(
            actor_id=actor_id,
            request_id=request_id,
            action="resource.availability",
            object_id=str(pool.pk),
            reason=command["reason"],
            payload_hash=digest,
            result={"status": "succeeded", "version": pool.version},
        )
        return result
