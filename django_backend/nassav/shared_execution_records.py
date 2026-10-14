"""Source -> pool -> shared work -> attempt fencing, with the legacy API preserved."""

from django.db import transaction
from nassav.db_retry import retry_sqlite_contention

from nassav.library_models import ResourcePoolEntry
from nassav.shared_work_models import SharedWork, WorkSubscription
from nassav.shared_work import specification_hash
from nassav.task_records import DjangoTaskRecords
from nassav.task_models import TaskArtifact
from nassav.resource_version_models import ResourceVersion
from nassav.task_control_rules import TaskExecutionInvalid


class SharedPublicationRejected(RuntimeError):
    """A still-owned executor must fail/stop, rather than silently abandon its job."""


class DjangoSharedExecutionRecords(DjangoTaskRecords):
    def __init__(self, source_context, *, reservation_lock=None):
        super().__init__(reservation_lock, shared_execution=True)
        self.source_context = source_context
        # Load keys and immutable source selection before taking pool/task locks.
        self.binding = source_context.work_binding

    def _authority(self, work):
        binding, spec = self.binding, work.spec
        if (
            spec.get("source") != binding["credential_refs"]["source_name"]
            or spec.get("credential_refs") != binding["credential_refs"]
            or spec.get("access_scope") != binding["access_scope"]
            or spec.get("context_revision") != binding["context_revision"]
            or work.credential_refs != binding["credential_refs"]
            or work.access_scope != binding["access_scope"]
            or work.spec_hash != specification_hash(spec)
            or work.job.options.get("spec") != spec
            or work.job.options.get("shared_work") is not True
            or work.job.owner_id is not None
            or work.job.kind != spec.get("kind")
            or work.job.action != spec.get("action")
            or work.job.avid != work.pool.canonical_avid
            or binding["actor_id"] != binding["owner_id"]
        ):
            raise SharedPublicationRejected("共享来源规范不匹配")

    def _work(self, job_id, *, locked=False):
        work = SharedWork.objects.filter(job_id=job_id).first()
        if work is None:
            raise SharedPublicationRejected("共享工作不存在")
        if locked:
            pool = ResourcePoolEntry.objects.select_for_update().get(pk=work.pool_id)
            work = SharedWork.objects.select_for_update().get(pk=work.pk)
        else:
            pool = work.pool
        self._authority(work)
        return work, pool

    def _demand(self, work, pool):
        if (
            pool.lifetime_generation != work.pool_generation
            or not pool.is_available
            or pool.state in {"deleting", "cleanup_failed", "reclaimed"}
        ):
            raise SharedPublicationRejected("共享资源代次已失效")
        demands = WorkSubscription.objects.filter(
            work=work,
            state="attached",
            operation__user__is_active=True,
            operation__membership__isnull=False,
        )
        if self.binding["owner_id"] is not None:
            demands = demands.filter(operation__user_id=self.binding["owner_id"])
        if not demands.exists():
            raise SharedPublicationRejected("共享工作已无有效需求")

    def _fenced(self, job_id, operation, *, allow_stopping=False):
        def locked():
            with transaction.atomic():
                work, pool = self._work(job_id, locked=True)
                if not allow_stopping:
                    self._demand(work, pool)
                return operation()

        return self.source_context.publish(locked)

    def claim(self, job_id, attempt_id, **kwargs):
        try:
            return self._fenced(
                job_id,
                lambda: super(DjangoSharedExecutionRecords, self).claim(
                    job_id, attempt_id, **kwargs
                ),
            )
        except SharedPublicationRejected as error:
            raise TaskExecutionInvalid(str(error)) from error

    @retry_sqlite_contention
    def check(self, token):
        super().check(token)  # Preserve pause/cancel priority and execution ownership.
        self.source_context.check()
        work, pool = self._work(token.job_id)
        self._demand(work, pool)

    def controlled_transaction(self, token, operation, **kwargs):
        def checked():
            result = operation()
            candidate = ResourceVersion.objects.filter(
                work__job_id=token.job_id
            ).first()
            targets = TaskArtifact.objects.filter(
                job_id=token.job_id, state__in=["promoting", "committed"]
            ).values_list("target_path", flat=True)
            prefix = f"versions/{candidate.pk}/" if candidate is not None else None
            if any(prefix is None or not path.startswith(prefix) for path in targets):
                raise SharedPublicationRejected("共享资产不得覆盖其他版本或旧路径")
            return result

        return self._fenced(
            token.job_id,
            lambda: super(DjangoSharedExecutionRecords, self).controlled_transaction(
                token, checked, **kwargs
            ),
            allow_stopping=kwargs.get("allow_stopping", False),
        )
