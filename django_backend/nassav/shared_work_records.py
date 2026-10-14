"""User -> pool -> work requests; no network, broker or filesystem under DB locks."""

from datetime import timedelta
from uuid import uuid5

from django.db import transaction
from django.db.models import F
from django.utils import timezone
from django.utils.crypto import salted_hmac

from nassav.db_retry import retry_sqlite_contention
from nassav.library_models import ResourcePoolEntry, UserLibraryEntry
from nassav.personal_state import lock_user
from nassav.shared_work import OperationConflict, OperationNotFound, specification_hash
from nassav.shared_work_models import (
    SharedWork,
    UserOperation,
    WorkSubscription,
    UserOperationCommand,
)
from nassav.task_models import TaskJob, TaskAttempt

TERMINAL = {"succeeded", "failed", "cancelled"}


def operation_snapshot(row):
    return {
        "operation_id": str(row.pk),
        "avid": row.pool.canonical_avid,
        "kind": row.kind,
        "action": row.action,
        "state": row.state,
        "stage": row.stage,
        "version": row.version,
        "message": row.message,
        "error_code": row.error_code or None,
        "allowed_actions": [] if row.state in TERMINAL else ["cancel"],
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


class DjangoOperationRecords:
    def __init__(self, task_records, *, gc_grace=timedelta(hours=24)):
        self.task_records = task_records
        self.gc_grace = gc_grace

    @retry_sqlite_contention
    def subscribe(self, user_id, command):
        spec = command["spec"]
        digest = salted_hmac(
            "nassav-user-operation", command["request_hash"]
        ).hexdigest()
        with transaction.atomic():
            lock_user(user_id)
            previous = UserOperation.objects.filter(
                user_id=user_id, request_id=command["request_id"]
            ).first()
            if previous:
                if previous.request_hash != digest:
                    raise OperationConflict("request_id_reused")
                return operation_snapshot(previous)
            if UserOperationCommand.objects.filter(
                user_id=user_id, request_id=command["request_id"]
            ).exists():
                raise OperationConflict("request_id_reused")
            if spec["access_scope"] != "public":
                raise OperationConflict("private_publication_not_ready")
            pool, _ = ResourcePoolEntry.objects.get_or_create(
                canonical_avid=command["avid"]
            )
            pool = ResourcePoolEntry.objects.select_for_update().get(pk=pool.pk)
            if not pool.is_available or pool.state in {"deleting", "cleanup_failed"}:
                raise OperationConflict("resource_unavailable")
            if pool.state in {"pending_gc", "reclaimed"}:
                pool.lifetime_generation += 1
                pool.version += 1
                pool.state = "ready" if pool.resource_id else "preparing"
                pool.gc_after = None
                pool.save()
            entry = UserLibraryEntry.objects.filter(user_id=user_id, pool=pool).first()
            desired = {"source": spec["source"]}
            if entry and (
                entry.desired_spec != desired
                or entry.access_scope != spec["access_scope"]
            ):
                raise OperationConflict("membership_spec_conflict")
            if spec["action"] != "add" and (entry is None or entry.state != "active"):
                raise OperationConflict("active_membership_required")
            entry = entry or UserLibraryEntry.objects.create(
                user_id=user_id,
                pool=pool,
                desired_spec=desired,
                access_scope=spec["access_scope"],
            )
            identity = specification_hash(
                {
                    "pool_id": str(pool.pk),
                    "generation": pool.lifetime_generation,
                    "spec": spec,
                }
            )
            work = (
                SharedWork.objects.select_for_update()
                .filter(active_key=identity)
                .first()
            )
            if work is not None and work.job.state in TERMINAL:
                work.active_key = None
                work.save(update_fields=["active_key", "updated_at"])
                work = None
            if work is not None and work.job.state == "cancelling":
                raise OperationConflict("shared_work_stopping")
            if work is None:
                # TaskAttempt is the existing durable dispatch outbox; no broker send.
                job = TaskJob.objects.create(
                    kind=spec["kind"],
                    avid=pool.canonical_avid,
                    action=spec["action"],
                    owner_id=None,
                    active_key=f"shared:{identity}",
                    options={
                        "source": spec["source"],
                        "shared_work": True,
                        "spec": spec,
                    },
                    timeline=[
                        {
                            "stage": "queued",
                            "state": "queued",
                            "at": timezone.now().timestamp(),
                        }
                    ],
                )
                TaskAttempt.objects.create(job=job, generation=1)
                work = SharedWork.objects.create(
                    pool=pool,
                    pool_generation=pool.lifetime_generation,
                    job=job,
                    spec_hash=command["spec_hash"],
                    spec=spec,
                    credential_refs=spec["credential_refs"],
                    access_scope=spec["access_scope"],
                    active_key=identity,
                )
            row = UserOperation.objects.create(
                user_id=user_id,
                pool=pool,
                membership=entry,
                request_id=command["request_id"],
                request_hash=digest,
                kind=spec["kind"],
                action=spec["action"],
                desired_spec=desired,
                access_scope=spec["access_scope"],
            )
            WorkSubscription.objects.create(operation=row, work=work)
            return operation_snapshot(row)

    def get(self, user_id, operation_id):
        row = UserOperation.objects.filter(pk=operation_id, user_id=user_id).first()
        if row is None:
            raise OperationNotFound("Operation not found")
        return operation_snapshot(row)

    @retry_sqlite_contention
    def cancel(self, user_id, operation_id, expected_version, request_id):
        digest = salted_hmac(
            "nassav-user-operation-cancel", f"{operation_id}:{expected_version}"
        ).hexdigest()
        with transaction.atomic():
            lock_user(user_id)
            previous = UserOperationCommand.objects.filter(
                user_id=user_id, request_id=request_id
            ).first()
            if previous:
                if previous.payload_hash != digest:
                    raise OperationConflict("request_id_reused")
                return previous.result
            if UserOperation.objects.filter(
                user_id=user_id, request_id=request_id
            ).exists():
                raise OperationConflict("request_id_reused")
            row = UserOperation.objects.filter(pk=operation_id, user_id=user_id).first()
            if row is None:
                raise OperationNotFound("Operation not found")
            pool = ResourcePoolEntry.objects.select_for_update().get(pk=row.pool_id)
            if row.version != expected_version:
                raise OperationConflict("operation_version_conflict")
            if row.state in TERMINAL:
                raise OperationConflict("operation_finished")
            subscription = WorkSubscription.objects.select_related("work").get(
                operation=row
            )
            work = SharedWork.objects.select_for_update().get(pk=subscription.work_id)
            subscription.state, subscription.detached_at = "detached", timezone.now()
            subscription.version += 1
            subscription.save()
            row.state, row.stage, row.finished_at = (
                "cancelled",
                "cancelled",
                timezone.now(),
            )
            row.version += 1
            row.save()
            if not WorkSubscription.objects.filter(
                work=work, state="attached"
            ).exists():
                snapshot = self.task_records.get(str(work.job_id))
                if snapshot["state"] not in TERMINAL:
                    self.task_records.request(
                        str(work.job_id),
                        "cancel",
                        expected_version=snapshot["version"],
                        request_id=str(uuid5(request_id, str(work.job_id))),
                        actor_id=None,
                        allow_all=True,
                    )
            self._release_pending(row, pool)
            result = operation_snapshot(row)
            UserOperationCommand.objects.create(
                user_id=user_id,
                operation=row,
                request_id=request_id,
                action="cancel",
                payload_hash=digest,
                result=result,
            )
            return result

    def _release_pending(self, row, pool):
        if row.membership_id is None:
            return
        entry = UserLibraryEntry.objects.filter(
            pk=row.membership_id, user_id=row.user_id, state="pending"
        ).first()
        if (
            entry is None
            or UserOperation.objects.filter(membership=entry)
            .exclude(state__in=TERMINAL)
            .exists()
        ):
            return
        entry.delete()
        row.membership_id = None
        if not pool.memberships.exists() and pool.state not in {
            "deleting",
            "cleanup_failed",
        }:
            pool.state, pool.gc_after = "pending_gc", timezone.now() + self.gc_grace
            pool.version = F("version") + 1
            pool.save(update_fields=["state", "gc_after", "version", "updated_at"])
