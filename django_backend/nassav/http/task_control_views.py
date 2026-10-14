"""Authenticated versioned controls; never expose workspace paths or media keys."""

from uuid import UUID, uuid5
from types import SimpleNamespace
from django.db.models import Case, When, IntegerField
import logging
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
from nassav.account_policy import can_admin_tasks
from nassav.account_policy import is_app_admin
from nassav.account_management import AccountConflict


from nassav.task_presentation import public_snapshot as public_snapshot
from nassav.admin_presentation import work_snapshot, work_snapshots


def authorized_snapshot(snapshot, user):
    return work_snapshot(public_snapshot(snapshot), user)


def authorized_job(request, job_id):
    if not request.user.is_authenticated:
        raise TaskForbidden("请先登录")
    try:
        job = TaskJob.objects.get(pk=job_id)
    except TaskJob.DoesNotExist as error:
        raise TaskNotFound("任务不存在") from error
    if job.owner_id != request.user.pk and not can_admin_tasks(request.user):
        from nassav.account_policy import is_legacy_operator

        if is_legacy_operator(request.user):
            raise TaskForbidden("无权读取此任务")
        raise TaskNotFound("任务不存在")
    return job


class TaskJobStatusView(SchemaAPIView):
    @extend_schema(operation_id="task_job_status")
    def get(self, request, job_id):
        try:
            authorized_job(request, job_id)
            return build_response(
                200,
                "success",
                authorized_snapshot(
                    build_task_records().get(str(job_id)), request.user
                ),
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
            if is_app_admin(request.user):
                from nassav.admin_work_commands import request_work

                snapshot = request_work(
                    request.user.pk, job_id, action, data, records=records
                )
            else:
                snapshot = records.request(
                    str(job_id),
                    action,
                    expected_version=version,
                    request_id=request_id,
                    actor_id=request.user.pk,
                    allow_all=can_admin_tasks(request.user),
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
            return build_response(
                202, "操作已登记", authorized_snapshot(snapshot, request.user)
            )
        except AccountConflict as error:
            return build_response(409, str(error), None)
        except TaskConflict as error:
            return build_response(
                409, str(error), authorized_snapshot(error.snapshot, request.user)
            )
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


class TaskJobListView(SchemaAPIView):
    @extend_schema(operation_id="task_job_list")
    def get(self, request):
        try:
            page = int(request.query_params.get("page", 1))
            size = int(request.query_params.get("page_size", 50))
            if page < 1 or not 1 <= size <= 100:
                raise ValueError("分页参数超出范围")
            ordering = request.query_params.get("ordering")
            if ordering is not None and ordering not in {"-created_at", "-updated_at"}:
                raise ValueError("排序仅支持创建时间或更新时间降序")
            jobs = TaskJob.objects.all()
            if not can_admin_tasks(request.user):
                jobs = jobs.filter(owner_id=request.user.pk)
            # Long-paused jobs must remain visible ahead of recent history.
            jobs = jobs.annotate(
                ended=Case(
                    When(state__in=TERMINAL_STATES, then=1),
                    default=0,
                    output_field=IntegerField(),
                )
            ).order_by(
                *([ordering, "id"] if ordering else ["ended", "-created_at", "id"])
            )
            total = jobs.count()
            records = build_task_records()
            snapshots = [
                public_snapshot(records.get(str(job_id)))
                for job_id in jobs.values_list("id", flat=True)[
                    (page - 1) * size : page * size
                ]
            ]
            snapshots = work_snapshots(snapshots, request.user)
            return build_response(
                200,
                "success",
                {
                    "jobs": snapshots,
                    "pagination": {
                        "page": page,
                        "page_size": size,
                        "total": total,
                        "has_more": page * size < total,
                    },
                },
            )
        except (ValueError, TypeError) as error:
            return build_response(400, str(error), None)


class TaskBatchControlView(SchemaAPIView):
    @extend_schema(operation_id="task_job_batch_action")
    def post(self, request):
        data = request.data or {}
        if not isinstance(data, dict):
            return build_response(400, "请求必须为对象", None)
        items = data.get("items")
        action = data.get("action")
        if (
            action not in {"pause", "resume", "cancel", "cleanup_retry"}
            or not isinstance(items, list)
            or not 1 <= len(items) <= 100
        ):
            return build_response(400, "批量操作须包含 1–100 个任务及有效动作", None)
        try:
            request_id = str(UUID(data.get("request_id", "")))
            ids = [str(UUID(item["job_id"])) for item in items]
            if len(set(ids)) != len(ids):
                raise ValueError("任务不能重复")
        except (ValueError, TypeError, AttributeError, KeyError):
            return build_response(400, "无效的任务或请求标识", None)
        results = []
        for item, job_id in zip(items, ids, strict=True):
            # Reuse the single-job command contract, including authorization and CAS.
            command_request = SimpleNamespace(
                user=request.user,
                data={
                    "request_id": str(uuid5(UUID(request_id), job_id))
                    if is_app_admin(request.user)
                    else request_id,
                    "expected_version": item.get("expected_version"),
                    **(
                        {"reason": data.get("reason")}
                        if is_app_admin(request.user)
                        else {}
                    ),
                },
            )
            try:
                response = TaskControlView().post(command_request, UUID(job_id), action)
                envelope = response.data
                results.append(
                    {
                        "job_id": job_id,
                        "code": response.status_code,
                        "message": envelope["message"],
                        "job": envelope["data"],
                    }
                )
            except Exception:
                logging.getLogger(__name__).exception(
                    "Batch task control failed: %s", job_id
                )
                results.append(
                    {
                        "job_id": job_id,
                        "code": 500,
                        "message": "操作未确认，可使用原请求标识重试",
                        "job": None,
                    }
                )
        return build_response(202, "批量操作已处理", {"results": results})
