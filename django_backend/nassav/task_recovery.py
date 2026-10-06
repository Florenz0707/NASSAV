"""Recover only proven stopped executions; dispatch, cleanup and events stay independent."""

import logging
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from nassav.task_control_rules import (
    ExecutionToken,
    TaskExecutionInvalid,
    TERMINAL_STATES,
)
from nassav.task_models import TaskAttempt, TaskJob, TaskEvent, TaskArtifact
from nassav.task_processes import identity_status, stop_owned_writers, TaskWritersAlive

logger = logging.getLogger(__name__)


def release_owned_download(identity, avid, client):
    owner = identity.get("lease_owner")
    if not owner:
        return
    task_key = f"nassav:task_lock:{avid}"
    # Keys are derived from the business ID, never arbitrary saved values.
    client.eval(
        """
        if redis.call('get',KEYS[1]) == ARGV[1] then
          redis.call('del',KEYS[1]); redis.call('del',KEYS[3]); redis.call('hdel',KEYS[4],ARGV[2])
        end
        if redis.call('get',KEYS[2]) == ARGV[1] then redis.call('del',KEYS[2]) end
        return 1
    """,
        4,
        task_key,
        "nassav:global_download_lock",
        f"nassav:task_progress:{avid}",
        "nassav:task_queue",
        owner,
        avid,
    )


class TaskRecovery:
    def __init__(
        self,
        records,
        assets,
        *,
        dispatch,
        events,
        redis_client,
        inspect=identity_status,
        stop_writers=stop_owned_writers,
        interrupt=None,
    ):
        self.records, self.assets = records, assets
        self.dispatch, self.events, self.redis_client = dispatch, events, redis_client
        self.inspect, self.stop_writers, self.interrupt = (
            inspect,
            stop_writers,
            interrupt,
        )

    def confirm_stopped(self, attempt_id: str, *, all_writers_stopped: bool):
        """Operator assertion for an old PID namespace, never an HTTP control shortcut."""
        if not all_writers_stopped:
            raise ValueError("必须明确确认原执行器和所有后代均已退出")
        attempt = TaskAttempt.objects.select_related("job").get(pk=attempt_id)
        if attempt.state != "running":
            return self.records.get(str(attempt.job_id))
        identity = attempt.execution_identity
        worker = {
            key.removeprefix("worker_"): value
            for key, value in identity.items()
            if key.startswith("worker_")
        }
        if self.inspect(worker) == "alive":
            raise TaskExecutionInvalid("记录的本地执行器仍在运行，不接受停止确认")
        cutoff = timezone.now() - timedelta(seconds=30)
        activity = attempt.heartbeat_at or attempt.started_at
        if activity is None or activity > cutoff:
            raise TaskExecutionInvalid("任务仍有近期心跳或启动记录，不接受停止确认")
        token = ExecutionToken(
            str(attempt.job_id),
            str(attempt.id),
            attempt.generation,
            str(attempt.execution_owner),
        )
        if self.inspect(worker) == "dead":
            self.stop_writers(
                {
                    "job_id": token.job_id,
                    "attempt_id": token.attempt_id,
                    "owner": token.owner,
                },
                identity,
            )
        if attempt.job.kind == "download":
            release_owned_download(identity, attempt.job.avid, self.redis_client())
        snapshot = self.records.recover_execution(
            token, identity=identity, stale_before=cutoff, interrupt=self.interrupt
        )
        self.assets.recover(token.job_id)
        if snapshot["cleanup_state"] == "pending":
            snapshot = self.assets.cleanup(token.job_id)
        return self.records.get(token.job_id)

    def scan(self, *, stale_seconds=30, retry_seconds=300, limit=100):
        if stale_seconds < 1 or retry_seconds < 1 or not 1 <= limit <= 1000:
            raise ValueError("恢复扫描参数超出范围")
        cutoff = timezone.now() - timedelta(seconds=stale_seconds)
        result = {
            "recovered": 0,
            "unconfirmed": 0,
            "alive": 0,
            "cleaned": 0,
            "events": 0,
            "failed": 0,
        }
        stale = (
            TaskAttempt.objects.filter(state="running")
            .filter(
                Q(heartbeat_at__lt=cutoff) | Q(heartbeat_at=None, started_at__lt=cutoff)
            )
            .select_related("job")
            .order_by("started_at")[:limit]
        )
        for attempt in stale:
            token = ExecutionToken(
                str(attempt.job_id),
                str(attempt.id),
                attempt.generation,
                str(attempt.execution_owner),
            )
            identity = attempt.execution_identity
            worker = {
                key.removeprefix("worker_"): value
                for key, value in identity.items()
                if key.startswith("worker_")
            }
            try:
                status = self.inspect(worker)
                if status == "alive":
                    result["alive"] += 1
                    continue
                if status != "dead":
                    raise TaskWritersAlive(
                        "执行器身份无法核查，保留状态与文件；请确认原实例退出后处理"
                    )
                self.stop_writers(
                    {
                        "job_id": token.job_id,
                        "attempt_id": token.attempt_id,
                        "owner": token.owner,
                    },
                    identity,
                )
                if attempt.job.kind == "download":
                    release_owned_download(
                        identity, attempt.job.avid, self.redis_client()
                    )
                self.records.recover_execution(
                    token,
                    identity=identity,
                    stale_before=cutoff,
                    interrupt=self.interrupt,
                )
                self.assets.recover(token.job_id)
                result["recovered"] += 1
            except TaskWritersAlive as error:
                try:
                    self.records.recovery_warning(token, str(error))
                except TaskExecutionInvalid:
                    pass
                result["unconfirmed"] += 1
            except TaskExecutionInvalid:
                pass  # A newer command/heartbeat/attempt won the race.
            except Exception:
                logger.exception("Task recovery failed: %s", token.job_id)
                result["failed"] += 1
        publications = (
            TaskArtifact.objects.filter(
                state="promoting", job__state__in={"paused", *TERMINAL_STATES}
            )
            .values_list("job_id", flat=True)
            .distinct()[:limit]
        )
        for job_id in publications:
            try:
                self.assets.recover(str(job_id))
                self.records.publication_recovery_status(str(job_id), failed=False)
            except TaskExecutionInvalid:
                continue
            except Exception:
                logger.exception("Stopped publication recovery failed: %s", job_id)
                try:
                    self.records.publication_recovery_status(str(job_id), failed=True)
                except TaskExecutionInvalid:
                    pass
                result["failed"] += 1
        self.records.retry_unclaimed(
            sent_before=timezone.now() - timedelta(seconds=retry_seconds)
        )
        try:
            result["dispatch"] = self.dispatch(self.records)
        except Exception:
            logger.exception("Pending task dispatch recovery failed")
            result["failed"] += 1
        cleanup = (
            TaskJob.objects.filter(state__in=TERMINAL_STATES)
            .filter(
                Q(cleanup_state="pending")
                | Q(cleanup_state="running", updated_at__lt=cutoff)
                | Q(
                    cleanup_state="failed",
                    updated_at__lt=timezone.now() - timedelta(seconds=retry_seconds),
                )
            )
            .order_by("updated_at")[:limit]
        )
        for job in cleanup:
            try:
                snapshot = self.assets.cleanup(str(job.id))
                result[
                    "cleaned" if snapshot["cleanup_state"] == "completed" else "failed"
                ] += 1
            except Exception:
                logger.exception("Private task cleanup failed: %s", job.id)
                result["failed"] += 1
        event_jobs = (
            TaskEvent.objects.filter(state="pending", job__resource_saved=True)
            .values_list("job_id", flat=True)
            .distinct()[:limit]
        )
        for job_id in event_jobs:
            try:
                self.events.flush(str(job_id))
                result["events"] += 1
            except Exception:
                logger.exception("Resource event retry failed: %s", job_id)
                result["failed"] += 1
        return result
