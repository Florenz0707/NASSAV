"""User -> pool -> work requests; no network, broker or filesystem under DB locks."""

from datetime import timedelta
from uuid import uuid5, uuid4

from django.db import transaction
from django.db.models import F, Q
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
PUBLIC_STAGES = {
    "queued",
    "running",
    "source",
    "source_complete",
    "metadata",
    "metadata_complete",
    "cover",
    "cover_complete",
    "avatars",
    "saving",
    "saved",
    "translation_queued",
    "translating",
    "translation_completed",
    "downloading",
    "validating",
    "resuming",
    "pausing",
    "paused",
    "cancelling",
    "succeeded",
    "failed",
    "cancelled",
}


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
    def __init__(
        self,
        task_records,
        *,
        gc_grace=timedelta(hours=24),
        hint=None,
        publication=None,
        allow_private=False,
    ):
        self.task_records = task_records
        self.gc_grace = gc_grace
        self.hint = hint
        self.publication = publication
        self.allow_private = allow_private

    def _hint(self, row):
        if self.hint is not None:
            hint = self.hint
            user_id = row.user_id
            data = {"operation_id": str(row.pk), "version": row.version}
            transaction.on_commit(lambda: hint(user_id, data), robust=True)

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
                if not self.allow_private or self.publication is None:
                    raise OperationConflict("private_publication_not_ready")
                from nassav.credential_models import SourceCredential

                ref = spec["credential_refs"]
                if (
                    not ref.get("credential_id")
                    or spec["access_scope"] != f"personal:{ref['credential_id']}"
                    or not SourceCredential.objects.filter(
                        pk=ref["credential_id"],
                        owner_id=user_id,
                        scope="personal",
                        version=ref["credential_version"],
                        origin_host=ref["origin_host"],
                        source_name=spec["source"],
                        state="active",
                    ).exists()
                ):
                    raise PermissionError("Credential scope not available")
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
            self._hint(row)
            return operation_snapshot(row)

    def get(self, user_id, operation_id):
        row = UserOperation.objects.filter(
            pk=operation_id, user_id=user_id, user__is_active=True
        ).first()
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
            self._detach(row, subscription, work, request_id)
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

    def _detach(self, row, subscription, work, request_id):
        subscription.state, subscription.detached_at = "detached", timezone.now()
        subscription.version += 1
        subscription.save()
        row.state = row.stage = "cancelled"
        row.finished_at = timezone.now()
        row.message, row.error_code = "请求已取消", ""
        row.version += 1
        row.save()
        self._hint(row)
        if not WorkSubscription.objects.filter(work=work, state="attached").exists():
            TaskJob.objects.select_for_update().get(pk=work.job_id)
            snapshot = self.task_records.get(str(work.job_id))
            if snapshot["state"] not in TERMINAL | {"cancelling"}:
                self.task_records.request(
                    str(work.job_id),
                    "cancel",
                    expected_version=snapshot["version"],
                    request_id=str(uuid5(request_id, str(work.job_id))),
                    actor_id=None,
                    allow_all=True,
                )

    @retry_sqlite_contention
    def detach_membership(self, user_id, entry_id):
        """Release/disable uses this inside the same user -> pool transaction.

        Keep the membership until its caller releases it, including active holds.
        No broker send, asset deletion or shared initiator ownership is implied.
        """
        with transaction.atomic():
            lock_user(user_id)
            entry = UserLibraryEntry.objects.filter(
                pk=entry_id, user_id=user_id
            ).first()
            if entry is None:
                return
            ResourcePoolEntry.objects.select_for_update().get(pk=entry.pool_id)
            subscriptions = (
                WorkSubscription.objects.filter(
                    operation__membership=entry,
                    operation__user_id=user_id,
                    state="attached",
                )
                .select_related("operation")
                .order_by("work_id", "pk")
            )
            for subscription in subscriptions:
                work = SharedWork.objects.select_for_update().get(
                    pk=subscription.work_id
                )
                self._detach(subscription.operation, subscription, work, uuid4())

    @retry_sqlite_contention
    def project(self, user_id, operation_id):
        """User-fenced projection; successful grants require the P5 publisher.

        It is deliberately not a global pool -> users transaction, which would
        invert the account/membership lock order. Repeated projections are no-ops.
        """
        with transaction.atomic():
            lock_user(user_id)
            row = UserOperation.objects.filter(pk=operation_id, user_id=user_id).first()
            if row is None:
                raise OperationNotFound("Operation not found")
            pool = ResourcePoolEntry.objects.select_for_update().get(pk=row.pool_id)
            subscription = WorkSubscription.objects.get(operation=row)
            work = SharedWork.objects.select_for_update().get(pk=subscription.work_id)
            job = TaskJob.objects.select_for_update().get(pk=work.job_id)
            if subscription.state != "attached" or row.state in TERMINAL:
                return operation_snapshot(row)
            if (
                pool.lifetime_generation != work.pool_generation
                or row.membership_id is None
                or not pool.is_available
                or pool.state in {"deleting", "cleanup_failed", "reclaimed"}
            ):
                self._detach(row, subscription, work, uuid4())
                self._release_pending(row, pool)
                return operation_snapshot(row)
            if job.state == "succeeded":
                if self.publication is None:
                    raise OperationConflict("publication_not_ready")
                self.publication.grant_locked(user_id, work, row.membership_id)
            state = job.state
            stage = job.stage if job.stage in PUBLIC_STAGES else state
            message = "共享工作失败，请重试" if state == "failed" else ""
            error_code = "WORK_FAILED" if state == "failed" else ""
            if (row.state, row.stage, row.message, row.error_code) == (
                state,
                stage,
                message,
                error_code,
            ):
                row.projected_work_version = job.version
                row.save(update_fields=["projected_work_version"])
                return operation_snapshot(row)
            row.state, row.stage, row.message, row.error_code = (
                state,
                stage,
                message,
                error_code,
            )
            row.projected_work_version = job.version
            row.version += 1
            if state in TERMINAL:
                row.stage, row.finished_at = state, timezone.now()
                subscription.state = "completed"
                subscription.version += 1
                subscription.save()
                work.active_key = None
            work.last_projected_version = max(work.last_projected_version, job.version)
            work.save()
            row.save()
            if state in TERMINAL:
                self._release_pending(row, pool)
            self._hint(row)
            return operation_snapshot(row)

    def project_pending(self, *, limit=100):
        if type(limit) is not int or not 1 <= limit <= 200:
            raise ValueError("Invalid projection batch size")
        candidates = (
            UserOperation.objects.filter(
                user__is_active=True, subscription__state="attached"
            )
            .exclude(state__in=TERMINAL)
            .filter(
                Q(projected_work_version__lt=F("subscription__work__job__version"))
                | Q(pool__is_available=False)
                | ~Q(pool__lifetime_generation=F("subscription__work__pool_generation"))
                | Q(membership__isnull=True)
            )
            .order_by("updated_at", "pk")
        )
        if self.publication is None:
            candidates = candidates.exclude(subscription__work__job__state="succeeded")
        candidates = candidates.values_list("user_id", "pk")[:limit]
        projected, skipped = 0, 0
        for user_id, operation_id in list(candidates):
            try:
                self.project(user_id, operation_id)
            except (PermissionError, OperationNotFound):
                # A concurrent disable/release may remove the demand after selection.
                skipped += 1
            else:
                projected += 1
        return {"projected": projected, "skipped": skipped}

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
