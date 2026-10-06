"""Authenticated versioned controls; never expose workspace paths or media keys."""

from uuid import UUID
from drf_spectacular.utils import extend_schema

from nassav.api_utils import build_response
from nassav.composition import build_task_assets, build_task_records
from nassav.http_base import SchemaAPIView
from nassav.task_control_rules import (
    TaskConflict,
    TaskForbidden,
    TaskNotFound,
    TERMINAL_STATES,
)
from nassav.task_models import TaskJob


from nassav.task_presentation import public_snapshot as public_snapshot


def authorized_job(request, job_id):
    if not request.user.is_authenticated:
        raise TaskForbidden("请先登录")
    try:
        job = TaskJob.objects.get(pk=job_id)
    except TaskJob.DoesNotExist as error:
        raise TaskNotFound("任务不存在") from error
    if job.owner_id != request.user.pk and not request.user.is_superuser:
        raise TaskForbidden("无权读取此任务")
    return job


class TaskJobStatusView(SchemaAPIView):
    @extend_schema(operation_id="task_job_status")
    def get(self, request, job_id):
        try:
            authorized_job(request, job_id)
            return build_response(
                200, "success", public_snapshot(build_task_records().get(str(job_id)))
            )
        except TaskForbidden as error:
            return build_response(403, str(error), None)
        except TaskNotFound as error:
            return build_response(404, str(error), None)


class TaskControlView(SchemaAPIView):
    @extend_schema(operation_id="task_job_action")
    def post(self, request, job_id, action):
        records = build_task_records()
        try:
            job = authorized_job(request, job_id)
            data = request.data or {}
            version = data.get("expected_version")
            if type(version) is not int or version < 1:
                raise ValueError("必须提供 expected_version 正整数")
            request_id = str(UUID(data.get("request_id", "")))
            snapshot = records.request(
                str(job_id),
                action,
                expected_version=version,
                request_id=request_id,
                actor_id=request.user.pk,
                allow_all=request.user.is_superuser,
            )
            if action == "resume":
                from nassav.task_dispatch import dispatch_downloads, dispatch_scrapes

                (dispatch_downloads if job.kind == "download" else dispatch_scrapes)(
                    records
                )
            # Stopped queued jobs have no writer; private cleanup is safe and retryable.
            if (
                snapshot["state"] in TERMINAL_STATES
                and snapshot["cleanup_state"] == "pending"
            ):
                snapshot = build_task_assets(records).cleanup(str(job_id))
            return build_response(202, "操作已登记", public_snapshot(snapshot))
        except TaskConflict as error:
            return build_response(409, str(error), public_snapshot(error.snapshot))
        except TaskForbidden as error:
            return build_response(403, str(error), None)
        except TaskNotFound as error:
            return build_response(404, str(error), None)
        except (ValueError, TypeError, AttributeError) as error:
            return build_response(400, str(error), None)


class TaskCleanupRetryView(TaskControlView):
    @extend_schema(operation_id="task_job_cleanup_retry")
    def post(self, request, job_id):
        return super().post(request, job_id, "cleanup_retry")
