"""Celery transports IDs; scoped workflow and DB own shared execution."""

from celery import shared_task
from django.conf import settings

from nassav.shared_work_models import SharedWork
from nassav.task_models import TaskJob, TaskAttempt
from nassav.shared_execution_records import SharedPublicationRejected
from nassav.credential_crypto import CredentialUnavailable
from nassav.task_control_rules import TaskExecutionInvalid
from nassav.db_retry import retry_sqlite_contention


@retry_sqlite_contention
def fail_unclaimed(job_id, attempt_id):
    from django.db import transaction
    from django.utils import timezone
    from nassav.library_models import ResourcePoolEntry

    with transaction.atomic():
        work = SharedWork.objects.filter(job_id=job_id).first()
        if work is None:
            return {"status": "ignored", "job_id": job_id}
        ResourcePoolEntry.objects.select_for_update().get(pk=work.pool_id)
        SharedWork.objects.select_for_update().get(pk=work.pk)
        job = TaskJob.objects.select_for_update().get(pk=job_id)
        attempt = TaskAttempt.objects.filter(
            pk=attempt_id,
            job=job,
            generation=job.generation,
            state__in=["pending", "sent"],
        ).first()
        if (
            job.state != "queued"
            or attempt is None
            or TaskAttempt.objects.filter(job=job, state="running").exists()
        ):
            return {"status": "ignored", "job_id": job_id}
        job.state, job.stage, job.error_code = (
            "failed",
            "failed",
            "SOURCE_CONTEXT_UNAVAILABLE",
        )
        job.message = "来源上下文已失效或不可用，请核对设置后重新提交"
        job.active_key = None
        job.finished_at = timezone.now()
        job.updated_at = timezone.now()
        job.version += 1
        if job.artifacts.exists():
            job.cleanup_state = "pending"
        job.save()
        attempt.state, attempt.stopped_at = "failed", timezone.now()
        attempt.save(update_fields=["state", "stopped_at"])
        return {"status": "failed", "job_id": job_id}


def execute_shared(job_id, attempt_id, *, builder):
    if not settings.SHARED_LIBRARY_ENABLED:
        return {"status": "ignored", "job_id": job_id}
    try:
        workflow = builder(job_id)
        result = workflow.run(job_id, attempt_id)
        if result.get("status") == "ignored":
            # Only a still-unclaimed current delivery may fail; duplicates and
            # old attempts cannot modify another executor or a resumed generation.
            return fail_unclaimed(job_id, attempt_id)
        return {
            "status": result.get("status", result.get("state", "failed")),
            "job_id": str(job_id),
        }
    except (
        CredentialUnavailable,
        PermissionError,
        ValueError,
        LookupError,
        SharedPublicationRejected,
        TaskExecutionInvalid,
    ):
        return fail_unclaimed(job_id, attempt_id)


@shared_task(bind=True, name="nassav.tasks.shared_work_task", ignore_result=True)
def shared_work_task(self, job_id):
    from nassav.composition import build_shared_workflow

    return execute_shared(job_id, self.request.id, builder=build_shared_workflow)
