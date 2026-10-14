"""Audited task controls, with broker/file work left to existing HTTP orchestration."""

import json
from uuid import UUID
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import F
from django.utils.crypto import salted_hmac
from nassav.account_models import (
    AccountControl,
    UserAccount,
    AdminCommandReceipt,
    AuditEvent,
)
from nassav.account_management import AccountConflict, REASONS
from nassav.library_models import ResourcePoolEntry
from nassav.task_models import TaskJob
from nassav.db_retry import retry_sqlite_contention


@retry_sqlite_contention
def request_work(actor_id, job_id, action, command, *, records):
    if not isinstance(command, dict) or set(command) != {
        "expected_version",
        "request_id",
        "reason",
    }:
        raise ValueError("Managed work control requires version, request ID and reason")
    if (
        not isinstance(command["reason"], str)
        or command["reason"] not in REASONS
        or type(command["expected_version"]) is not int
        or command["expected_version"] < 1
    ):
        raise ValueError("Invalid managed work command")
    request_id, job_id = UUID(str(command["request_id"])), UUID(str(job_id))
    digest = salted_hmac(
        "nassav-admin-command",
        json.dumps(["work", str(job_id), action, command], sort_keys=True),
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
        job = TaskJob.objects.get(pk=job_id)
        # Pool must precede the work row; existing work-only paths never lock it backwards.
        list(
            ResourcePoolEntry.objects.select_for_update().filter(
                canonical_avid=job.avid
            )
        )
        prior = AdminCommandReceipt.objects.filter(
            actor_id=actor_id, request_id=request_id
        ).first()
        if prior:
            if prior.payload_hash != digest:
                raise AccountConflict("request_id_conflict")
            return records.get(str(job_id))
        snapshot = records.request(
            str(job_id),
            action,
            expected_version=command["expected_version"],
            request_id=str(request_id),
            actor_id=actor_id,
            allow_all=True,
        )
        result = {key: snapshot[key] for key in ("job_id", "version", "state")}
        AdminCommandReceipt.objects.create(
            actor_id=actor_id, request_id=request_id, payload_hash=digest, result=result
        )
        AuditEvent.objects.create(
            actor_id=actor_id,
            request_id=request_id,
            action=f"work.{action}",
            object_id=str(job_id),
            reason=command["reason"],
            payload_hash=digest,
            result={"status": "succeeded", **result},
        )
        return snapshot
