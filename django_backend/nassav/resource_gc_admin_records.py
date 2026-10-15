"""Admin control -> user -> pool fences; no private metadata or broker in audit."""

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
from nassav.db_retry import retry_sqlite_contention
from nassav.resource_gc_models import ResourceGcJob
from nassav.resource_gc_admin import GcAdminConflict
from nassav.resource_gc_records import gc_snapshot


class DjangoGcAdminCommands:
    def __init__(self, records):
        self.records = records

    @retry_sqlite_contention
    def execute(self, actor_id, action, target_id, command):
        digest = salted_hmac(
            "nassav-gc-admin", json.dumps([action, target_id, command], sort_keys=True)
        ).hexdigest()
        with transaction.atomic():
            AccountControl.objects.get_or_create(pk=1)
            AccountControl.objects.filter(pk=1).update(version=F("version"))
            User = get_user_model()
            if (
                not User.objects.filter(pk=actor_id, is_active=True).update(
                    last_login=F("last_login")
                )
                or not UserAccount.objects.filter(
                    user_id=actor_id, role="admin"
                ).exists()
            ):
                raise PermissionError("Application admin required")
            prior = AdminCommandReceipt.objects.filter(
                actor_id=actor_id, request_id=command["request_id"]
            ).first()
            if prior:
                if prior.payload_hash != digest:
                    raise GcAdminConflict("request_id_conflict")
                return prior.result, False
            if action == "retry":
                candidate = self.records.intent(target_id)
                pool = self.records.lock_pool(candidate.pool_id)
                job = ResourceGcJob.objects.select_for_update().get(pk=target_id)
                if job.revision != command["expected_version"]:
                    raise GcAdminConflict("gc_revision_conflict")
                if job.state != "cleanup_failed" or job.owner is not None:
                    raise GcAdminConflict("gc_not_retryable")
                job.state, job.error_code = "queued", ""
                job.revision += 1
                job.save()
                result = gc_snapshot(job)
                send = True
            else:
                pool = self.records.lock_pool(UUID(target_id))
                if pool.version != command["expected_version"]:
                    raise GcAdminConflict("pool_version_conflict")
                if action == "retention":
                    if (
                        pool.state == "deleting"
                        or ResourceGcJob.objects.filter(
                            pool=pool, state="deleting"
                        ).exists()
                    ):
                        raise GcAdminConflict("gc_already_deleting")
                    pool.retained = command["retained"]
                    pool.version += 1
                    pool.save(update_fields=["retained", "version", "updated_at"])
                    result = {
                        "pool_id": str(pool.pk),
                        "pool_version": pool.version,
                        "retained": pool.retained,
                    }
                    send = False
                else:
                    result = self.records.enqueue(pool.pk, command.get("version_id"))
                    send = result["state"] == "queued"
            AdminCommandReceipt.objects.create(
                actor_id=actor_id,
                request_id=command["request_id"],
                payload_hash=digest,
                result=result,
            )
            AuditEvent.objects.create(
                actor_id=actor_id,
                request_id=command["request_id"],
                action=f"gc_{action}",
                object_id=target_id,
                reason=command["reason"],
                payload_hash=digest,
                result=result,
            )
            return result, send
