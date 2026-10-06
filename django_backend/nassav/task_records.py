"""Django Adapter for durable task controls and fenced worker checkpoints.

The public interface owns DB transitions. Dispatch accepts an explicit callable;
this module does not import Celery or publish inside a database transaction.
"""

import time
from collections.abc import Callable
from functools import wraps
from uuid import UUID, uuid4

from django.db import IntegrityError, OperationalError, connection, transaction
from django.core.exceptions import ValidationError
from django.utils import timezone

from nassav.task_control_rules import (
    ExecutionToken,
    TaskCancelRequested,
    TaskConflict,
    TaskExecutionInvalid,
    TaskForbidden,
    TaskNotFound,
    TaskPauseRequested,
    TERMINAL_STATES,
    allowed_actions,
    command_state,
    normalize_avid,
)
from nassav.task_models import TaskAttempt, TaskCommand, TaskJob


def _retry_sqlite_contention(method):
    @wraps(method)
    def retry(*args, **kwargs):
        for attempt in range(8):
            try:
                return method(*args, **kwargs)
            except OperationalError as error:
                if (
                    connection.vendor != "sqlite"
                    or "locked" not in str(error).lower()
                    or attempt == 7
                ):
                    raise
                time.sleep(0.01 * (attempt + 1))

    return retry


class DjangoTaskRecords:
    """Control/read interface plus an execution interface using ExecutionToken."""

    @staticmethod
    def _row(job_id: str) -> TaskJob:
        try:
            return TaskJob.objects.get(pk=job_id)
        except (TaskJob.DoesNotExist, ValueError, ValidationError) as error:
            raise TaskNotFound("任务不存在") from error

    @staticmethod
    def _snapshot(row: TaskJob) -> dict:
        attempt = row.attempts.filter(generation=row.generation, role="main").first()
        return {
            "job_id": str(row.id),
            "task_id": str(attempt.id) if attempt else None,
            "job_type": row.kind,
            "avid": row.avid,
            "action": row.action,
            "state": row.state,
            "stage": row.stage or None,
            "version": row.version,
            "generation": row.generation,
            "requested_action": row.requested_action or None,
            "checkpoint": row.checkpoint,
            "timeline": row.timeline,
            "resource_saved": row.resource_saved,
            "translation": row.translation,
            "error_code": row.error_code or None,
            "message": row.message or None,
            "cleanup_state": row.cleanup_state,
            "cleanup_message": row.cleanup_message or None,
            "created_at": row.created_at.timestamp(),
            "updated_at": row.updated_at.timestamp(),
            "finished_at": row.finished_at.timestamp() if row.finished_at else None,
            "allowed_actions": allowed_actions(row.state, row.cleanup_state),
        }

    def get(self, job_id: str) -> dict:
        return self._snapshot(self._row(job_id))

    @staticmethod
    def _event(row: TaskJob, state: str, stage: str | None = None) -> list:
        return [
            *row.timeline,
            {"state": state, "stage": stage or state, "at": timezone.now().timestamp()},
        ]

    def _update(self, row: TaskJob, **changes) -> TaskJob:
        changes.update(version=row.version + 1, updated_at=timezone.now())
        if not TaskJob.objects.filter(pk=row.pk, version=row.version).update(**changes):
            raise TaskConflict("任务已更新，请重新读取", self.get(str(row.id)))
        return self._row(str(row.id))

    @_retry_sqlite_contention
    def create(
        self,
        kind: str,
        avid: str,
        *,
        owner_id: int | None,
        action: str,
        options: dict | None = None,
    ) -> tuple[dict, bool]:
        avid = normalize_avid(avid)
        if kind not in {"download", "scrape"} or action not in (
            {"download", "mock"} if kind == "download" else {"add", "refresh"}
        ):
            raise ValueError("任务类型或操作无效")
        active_key = f"{kind}:{avid}"
        try:
            with transaction.atomic():
                now = timezone.now().timestamp()
                row = TaskJob.objects.create(
                    kind=kind,
                    avid=avid,
                    action=action,
                    owner_id=owner_id,
                    active_key=active_key,
                    options=options or {},
                    timeline=[{"stage": "queued", "state": "queued", "at": now}],
                )
                TaskAttempt.objects.create(job=row, generation=1)
                return self._snapshot(row), False
        except IntegrityError:
            existing = TaskJob.objects.filter(active_key=active_key).first()
            if existing:
                # The dedupe reservation also covers paused jobs.
                if existing.owner_id != owner_id:
                    raise TaskForbidden("该资源任务属于其他操作者")
                return self._snapshot(existing), True
            raise

    @_retry_sqlite_contention
    def request(
        self,
        job_id: str,
        action: str,
        *,
        expected_version: int,
        request_id: str,
        actor_id: int | None,
        allow_all: bool = False,
    ) -> dict:
        request_uuid = UUID(request_id)
        if action not in {"pause", "resume", "cancel", "cleanup_retry"}:
            raise ValueError("无效的任务控制动作")
        with transaction.atomic():
            row = self._row(job_id)
            if not allow_all and (actor_id is None or row.owner_id != actor_id):
                raise TaskForbidden("无权控制此任务")
            previous = row.commands.filter(request_id=request_uuid).first()
            if previous:
                if previous.action != action:
                    raise TaskConflict("请求编号已经用于其他操作", self._snapshot(row))
                return self._snapshot(row)
            if expected_version != row.version:
                raise TaskConflict("任务版本已变化", self._snapshot(row))
            has_writer = row.attempts.filter(state="running").exists()
            try:
                if action == "cleanup_retry":
                    if action not in allowed_actions(row.state, row.cleanup_state):
                        raise ValueError("当前状态不允许重试清理")
                    state = row.state
                else:
                    state = command_state(row.state, action, has_writer)
            except ValueError as error:
                raise TaskConflict(str(error), self._snapshot(row)) from error
            changes: dict = {}
            if action == "resume" and row.artifacts.filter(state="promoting").exists():
                raise TaskConflict("需要先恢复未完成文件提交", self._snapshot(row))
            if action == "cleanup_retry":
                changes.update(cleanup_state="pending", cleanup_message="")
            if state != row.state:
                changes.update(state=state, timeline=self._event(row, state))
            if action == "resume":
                changes.update(
                    generation=row.generation + 1,
                    requested_action="",
                    error_code="",
                    message="",
                )
            elif state not in TERMINAL_STATES:
                changes["requested_action"] = action
            if state == "cancelled" and action != "cleanup_retry":
                pending_files = row.artifacts.exclude(
                    state__in=["committed", "deleted"]
                ).exists()
                changes.update(
                    active_key=None,
                    requested_action="cancel",
                    finished_at=timezone.now(),
                    cleanup_state="pending" if pending_files else "not_required",
                )
            row = self._update(row, **changes)
            if action in {"pause", "cancel"}:
                row.attempts.filter(state__in=["pending", "sent"]).update(
                    state="invalidated", stopped_at=timezone.now()
                )
            if action == "resume":
                TaskAttempt.objects.create(job=row, generation=row.generation)
            TaskCommand.objects.create(
                job=row, request_id=request_uuid, action=action, version=row.version
            )
            return self._snapshot(row)

    @_retry_sqlite_contention
    def claim(
        self, job_id: str, attempt_id: str, *, owner: str | None = None
    ) -> ExecutionToken:
        owner_uuid = UUID(owner) if owner else uuid4()
        with transaction.atomic():
            row = self._row(job_id)
            attempt = row.attempts.filter(
                pk=attempt_id, generation=row.generation, state__in=["pending", "sent"]
            ).first()
            if (
                attempt is None
                or row.state != "queued"
                or row.artifacts.filter(state="promoting").exists()
            ):
                raise TaskExecutionInvalid("执行已失效或已经领取")
            self._update(row, state="running", timeline=self._event(row, "running"))
            now = timezone.now()
            updated = TaskAttempt.objects.filter(
                pk=attempt.pk, state__in=["pending", "sent"]
            ).update(
                state="running",
                execution_owner=owner_uuid,
                started_at=now,
                heartbeat_at=now,
            )
            if not updated:
                raise TaskExecutionInvalid("执行已被领取")
            return ExecutionToken(
                str(row.id), str(attempt.id), row.generation, str(owner_uuid)
            )

    @staticmethod
    def _execution(row: TaskJob, token: ExecutionToken) -> TaskAttempt:
        attempt = row.attempts.filter(
            pk=token.attempt_id,
            generation=token.generation,
            execution_owner=token.owner,
            state="running",
        ).first()
        if row.generation != token.generation or attempt is None:
            raise TaskExecutionInvalid("旧执行不得更新当前任务")
        return attempt

    @staticmethod
    def _continue(row: TaskJob) -> None:
        if row.state == "pausing":
            raise TaskPauseRequested("请求暂停")
        if row.state == "cancelling":
            raise TaskCancelRequested("请求终止")
        if row.state != "running":
            raise TaskExecutionInvalid("任务不在执行中")

    def check(self, token: ExecutionToken) -> None:
        row = self._row(token.job_id)
        self._execution(row, token)
        self._continue(row)

    def owned(self, token: ExecutionToken) -> None:
        """Permit private checkpoint recording while a stop request is pending."""
        self._execution(self._row(token.job_id), token)

    def controlled_transaction(
        self,
        token: ExecutionToken,
        operation: Callable,
        *,
        checkpoint: dict | None = None,
        resource_saved: bool = False,
        allow_stopping: bool = False,
    ):
        """Fence a short commit callback; filesystem compensation belongs to its caller."""
        with transaction.atomic():
            row = self._row(token.job_id)
            self._execution(row, token)
            if not allow_stopping:
                self._continue(row)
            # Obtain the DB write fence before the callback can publish files.
            row = self._update(row)
            result = operation()
            self._update(
                row,
                checkpoint={**row.checkpoint, **(checkpoint or {})},
                resource_saved=row.resource_saved or resource_saved,
            )
            return result

    def stopped_transaction(self, job_id: str, operation: Callable):
        """Fence recovery against resume/claim without inventing an execution owner."""
        with transaction.atomic():
            row = self._row(job_id)
            if row.attempts.filter(state="running").exists():
                raise TaskExecutionInvalid("执行未确认退出")
            self._update(row)
            return operation()

    def set_cleanup(self, job_id: str, state: str, message: str = "") -> dict:
        if state not in {"not_required", "pending", "running", "completed", "failed"}:
            raise ValueError("无效的清理状态")
        with transaction.atomic():
            row = self._row(job_id)
            if (
                row.state not in TERMINAL_STATES
                or row.attempts.filter(state="running").exists()
            ):
                raise TaskExecutionInvalid("执行停止前不能清理")
            return self._snapshot(
                self._update(row, cleanup_state=state, cleanup_message=message)
            )

    @_retry_sqlite_contention
    def checkpoint(
        self, token: ExecutionToken, stage: str, data: dict | None = None
    ) -> dict:
        with transaction.atomic():
            row = self._row(token.job_id)
            self._execution(row, token)
            self._continue(row)
            changes = {"stage": stage, "checkpoint": {**row.checkpoint, **(data or {})}}
            if stage != row.stage:
                changes["timeline"] = self._event(row, "running", stage)
            return self._snapshot(self._update(row, **changes))

    @_retry_sqlite_contention
    def acknowledge_stop(
        self, token: ExecutionToken, *, checkpoint: dict | None = None
    ) -> dict:
        """Caller must first confirm its process/network writers have exited."""
        with transaction.atomic():
            row = self._row(token.job_id)
            attempt = self._execution(row, token)
            if row.state not in {"pausing", "cancelling"}:
                raise TaskExecutionInvalid("未收到停止请求")
            state = "paused" if row.state == "pausing" else "cancelled"
            changes: dict = {
                "state": state,
                "timeline": self._event(row, state),
                "checkpoint": {**row.checkpoint, **(checkpoint or {})},
            }
            if state == "cancelled":
                pending_files = row.artifacts.exclude(
                    state__in=["committed", "deleted"]
                ).exists()
                changes.update(
                    active_key=None,
                    finished_at=timezone.now(),
                    cleanup_state="pending" if pending_files else "not_required",
                )
            row = self._update(row, **changes)
            TaskAttempt.objects.filter(
                pk=attempt.pk, execution_owner=token.owner, state="running"
            ).update(state="stopped", stopped_at=timezone.now())
            return self._snapshot(row)

    @_retry_sqlite_contention
    def finish(
        self,
        token: ExecutionToken,
        state: str,
        *,
        error_code: str = "",
        message: str = "",
    ) -> dict:
        if state not in {"succeeded", "failed"}:
            raise ValueError("无效的执行终态")
        with transaction.atomic():
            row = self._row(token.job_id)
            attempt = self._execution(row, token)
            self._continue(row)
            row = self._update(
                row,
                state=state,
                active_key=None,
                finished_at=timezone.now(),
                timeline=self._event(row, state),
                error_code=error_code,
                message=message,
                cleanup_state="pending" if row.artifacts.exists() else "not_required",
            )
            TaskAttempt.objects.filter(
                pk=attempt.pk, execution_owner=token.owner, state="running"
            ).update(state=state, stopped_at=timezone.now())
            return self._snapshot(row)

    def heartbeat(self, token: ExecutionToken) -> bool:
        return bool(
            TaskAttempt.objects.filter(
                pk=token.attempt_id,
                job_id=token.job_id,
                job__generation=token.generation,
                generation=token.generation,
                execution_owner=token.owner,
                state="running",
            ).update(heartbeat_at=timezone.now())
        )

    def dispatch_pending(
        self, send: Callable[[dict], None], *, limit: int = 100
    ) -> dict:
        """Outbox-like attempts persist before publish; duplicate publish is safe at claim."""
        sent, failed = 0, 0
        attempts = (
            TaskAttempt.objects.filter(state="pending", job__state="queued")
            .select_related("job")
            .order_by("job__created_at")[:limit]
        )
        for attempt in attempts:
            if attempt.generation != attempt.job.generation:
                continue
            ticket = {
                "job_id": str(attempt.job_id),
                "task_id": str(attempt.id),
                "generation": attempt.generation,
                "role": attempt.role,
                "kind": attempt.job.kind,
                "avid": attempt.job.avid,
                "action": attempt.job.action,
                "options": attempt.job.options,
            }
            try:
                send(ticket)
            except Exception as error:
                TaskAttempt.objects.filter(pk=attempt.pk, state="pending").update(
                    dispatch_error=str(error)[:200]
                )
                failed += 1
            else:
                TaskAttempt.objects.filter(pk=attempt.pk, state="pending").update(
                    state="sent", dispatched_at=timezone.now(), dispatch_error=""
                )
                sent += 1
        return {"sent": sent, "failed": failed}
