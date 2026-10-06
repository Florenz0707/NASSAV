"""Submission, Redis snapshots, and worker execution for resource scrape jobs."""

import json
import time
from abc import ABC, abstractmethod
from typing import cast
from uuid import uuid4

import redis
from celery import shared_task
from django.conf import settings
from django.core import signing
from loguru import logger

from nassav.models import AVResource
from nassav.resource_service import (
    ResourceAccessDeniedError,
    ResourceAlreadyExistsError,
    ResourceFetchError,
    ResourceNotFoundError,
)

SNAPSHOT_TTL = 86400
LOCK_TTL = 14400
TERMINAL_STATES = {"succeeded", "failed", "cancelled"}
_RELEASE_LOCK = "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end"
_RENEW_LOCK = "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('expire', KEYS[1], ARGV[2]) else return 0 end"


class JobStore(ABC):
    """Persistence boundary for scrape job snapshots and per-resource ownership."""

    @abstractmethod
    def acquire(self, avid: str, task_id: str) -> str | None: ...

    @abstractmethod
    def release(self, avid: str, task_id: str) -> None: ...

    @abstractmethod
    def get(self, task_id: str) -> dict | None: ...

    @abstractmethod
    def save(self, snapshot: dict) -> dict: ...

    @abstractmethod
    def delete(self, task_id: str) -> None: ...

    @abstractmethod
    def renew(self, avid: str, task_id: str) -> bool: ...


class RedisJobStore(JobStore):
    """Redis implementation with owner-checked locks and versioned snapshots."""

    def __init__(self):
        self.client = redis.from_url(settings.CELERY_BROKER_URL)

    @staticmethod
    def _lock_key(avid: str) -> str:
        return f"nassav:scrape:lock:{avid}"

    @staticmethod
    def _status_key(task_id: str) -> str:
        return f"nassav:scrape:job:{task_id}"

    def acquire(self, avid: str, task_id: str) -> str | None:
        key = self._lock_key(avid)
        if self.client.set(key, task_id, nx=True, ex=LOCK_TTL):
            return None
        owner = cast(bytes | None, self.client.get(key))
        return owner.decode() if owner else ""

    def release(self, avid: str, task_id: str) -> None:
        self.client.eval(_RELEASE_LOCK, 1, self._lock_key(avid), task_id)

    def renew(self, avid: str, task_id: str) -> bool:
        return bool(
            self.client.eval(_RENEW_LOCK, 1, self._lock_key(avid), task_id, LOCK_TTL)
        )

    def get(self, task_id: str) -> dict | None:
        value = cast(bytes | None, self.client.get(self._status_key(task_id)))
        return json.loads(value) if value else None

    def save(self, snapshot: dict) -> dict:
        key = self._status_key(snapshot["task_id"])
        while True:
            with self.client.pipeline() as pipe:
                try:
                    pipe.watch(key)
                    existing_data = cast(bytes | None, pipe.get(key))
                    existing = json.loads(existing_data) if existing_data else None
                    if existing and existing["state"] in TERMINAL_STATES:
                        return existing
                    current = dict(snapshot)
                    current["version"] = (existing or {}).get("version", 0) + 1
                    current["updated_at"] = time.time()
                    pipe.multi()
                    pipe.setex(key, SNAPSHOT_TTL, json.dumps(current))
                    pipe.execute()
                    return current
                except redis.WatchError:
                    continue

    def delete(self, task_id: str) -> None:
        self.client.delete(self._status_key(task_id))


def job_token(task_id: str) -> str:
    """Issue a signed capability for reading one task snapshot."""
    return signing.dumps(task_id, salt="nassav.scrape.job")


def valid_job_token(task_id: str, token: str) -> bool:
    try:
        return (
            signing.loads(
                token, salt="nassav.scrape.job", max_age=SNAPSHOT_TTL + LOCK_TTL + 1860
            )
            == task_id
        )
    except signing.BadSignature:
        return False


def _publish(snapshot: dict) -> None:
    from nassav.consumers import send_task_update

    # The existing WebSocket group is global. Publish only routing/progress fields;
    # the snapshot API requires the signed capability returned to the submitter.
    event = {
        key: snapshot[key]
        for key in ("task_id", "job_type", "state", "stage", "version", "updated_at")
    }
    try:
        send_task_update("scrape_job_update", event)
    except Exception:
        logger.exception("刮削任务状态已保存，但 WebSocket 推送失败")


def _update(store: JobStore, snapshot: dict, **changes) -> dict:
    updated = {**snapshot, **changes}
    if (updated["state"], updated.get("stage")) != (
        snapshot["state"],
        snapshot.get("stage"),
    ):
        stage = (
            updated["state"]
            if updated["state"] in {"failed", "cancelled"}
            else updated.get("stage")
            or (
                "resource_saved"
                if updated["state"] == "succeeded"
                else updated["state"]
            )
        )
        updated["timeline"] = [
            *snapshot.get("timeline", []),
            {"stage": stage, "state": updated["state"], "at": time.time()},
        ]
    current = store.save(updated)
    if current["state"] == changes.get("state", snapshot["state"]):
        _publish(current)
    return current


def submit_resource_job(
    action: str,
    avid: str,
    source: str = "any",
    options: dict | None = None,
    *,
    store: JobStore | None = None,
) -> tuple[dict, bool]:
    """Validate and queue one resource operation; returns (snapshot, duplicate)."""
    action = action.lower()
    avid = avid.strip().upper()
    source = source.strip().lower()
    if action not in {"add", "refresh"} or not avid or len(avid) > 50:
        raise ValueError("无效的操作或资源编号")
    store = store or RedisJobStore()
    task_id = str(uuid4())
    owner = store.acquire(avid, task_id)
    if owner is not None:
        existing = store.get(owner) if owner else None
        if existing:
            return existing, True
        raise RuntimeError("资源任务锁已占用，请稍后重试")
    try:
        if action == "add" and AVResource.objects.filter(avid=avid).exists():
            raise ResourceAlreadyExistsError(avid, {"avid": avid})
        if action == "refresh" and not AVResource.objects.filter(avid=avid).exists():
            raise ResourceNotFoundError(avid, {"database": 404})
    except Exception:
        store.release(avid, task_id)
        raise
    snapshot = {
        "task_id": task_id,
        "job_type": "scrape",
        "action": action,
        "avid": avid,
        "state": "queued",
        "stage": None,
        "resource_avid": None,
        "error_code": None,
        "message": None,
        "translation": {"state": "not_requested"},
        "timeline": [{"stage": "queued", "state": "queued", "at": time.time()}],
    }
    try:
        snapshot = store.save(snapshot)
        run_resource_job.apply_async(
            args=(action, avid, source, options or {}),
            task_id=task_id,
            queue="scrape",
            expires=LOCK_TTL,
        )
    except Exception:
        store.delete(task_id)
        store.release(avid, task_id)
        raise
    _publish(snapshot)
    return snapshot, False


def get_resource_job(task_id: str, *, store: JobStore | None = None) -> dict | None:
    store = store or RedisJobStore()
    snapshot = store.get(task_id)
    if snapshot and snapshot["state"] in {"queued", "running"}:
        # A worker lost after early acknowledgement leaves no terminal event.
        # Expired ownership makes this failure visible and permits resubmission.
        owner = store.acquire(snapshot["avid"], task_id)
        if owner is None:
            snapshot = _update(
                store,
                snapshot,
                state="failed",
                error_code="WORKER_LOST",
                message="任务已过期，请重新提交",
            )
            store.release(snapshot["avid"], task_id)
        elif owner != task_id:
            snapshot = _update(
                store,
                snapshot,
                state="failed",
                error_code="JOB_EXPIRED",
                message="任务锁已过期，请重新提交",
            )
    if snapshot:
        from nassav.resource_job_details import resource_job_details

        return resource_job_details(snapshot)
    return None


@shared_task(
    bind=True,
    name="nassav.scrape_jobs.run_resource_job",
    soft_time_limit=1800,
    time_limit=1860,
)
def run_resource_job(self, action: str, avid: str, source: str, options: dict):
    """Run existing ResourceService in the scrape worker; task args are JSON only."""
    from celery.exceptions import SoftTimeLimitExceeded

    from nassav.resource_service import resource_service
    from nassav.tasks import translate_title_task

    store = RedisJobStore()
    task_id = self.request.id
    active_snapshot = store.get(task_id)
    if not active_snapshot or active_snapshot["state"] in TERMINAL_STATES:
        return
    if not store.renew(avid, task_id):
        return
    snapshot: dict = active_snapshot
    queue_wait_ms = round(
        max(0, time.time() - active_snapshot.get("updated_at", time.time())) * 1000
    )
    scrape_started = time.monotonic()

    translation_requested = False

    def progress(stage: str) -> None:
        nonlocal snapshot, translation_requested
        if stage == "translation_queued":
            translation_requested = True
        if not store.renew(avid, task_id):
            raise RuntimeError("任务锁已过期")
        snapshot = _update(store, snapshot, state="running", stage=stage)

    snapshot = _update(store, snapshot, state="running")
    result: dict
    try:
        if action == "add":
            # A prior delivery may have saved the resource before losing its worker.
            if AVResource.objects.filter(avid=avid).exists():
                result = {"resource": {"avid": avid}}
            else:
                result = resource_service.add_resource(avid, source, progress=progress)
        else:
            if options.get("refresh_metadata", True) or options.get(
                "refresh_m3u8", True
            ):
                result = resource_service.refresh_resource(
                    avid,
                    scrape=options.get("refresh_metadata", True),
                    download_cover=options.get("refresh_metadata", True),
                    progress=progress,
                )
            else:
                result = {"resource": {"avid": avid}}
            if options.get("retranslate", False):
                resource = AVResource.objects.get(avid=avid)
                resource.translation_status = "pending"
                resource.translated_title = None
                resource.save(update_fields=["translation_status", "translated_title"])
                progress("translation_queued")
                try:
                    result["translate_task_id"] = translate_title_task.delay(avid).id
                except Exception:
                    logger.exception("资源已保存，但翻译任务未能入队: {}", avid)
        translation_id = result.get("translate_task_id")
        translation = (
            {"task_id": translation_id, "state": "queued"}
            if translation_id
            else {
                "state": "failed",
                "message": "翻译任务未能入队",
                "completed_at": time.time(),
            }
            if translation_requested
            else {"state": "not_requested"}
        )
        snapshot = _update(
            store,
            snapshot,
            state="succeeded",
            stage=None,
            resource_avid=result["resource"]["avid"],
            resource={
                key: result["resource"].get(key)
                for key in (
                    "avid",
                    "original_title",
                    "source_title",
                    "translated_title",
                )
            },
            translation=translation,
        )
        return {"resource_avid": snapshot["resource_avid"]}
    except (
        ResourceNotFoundError,
        ResourceAlreadyExistsError,
        ResourceAccessDeniedError,
        ResourceFetchError,
    ) as exc:
        code = exc.__class__.__name__.removesuffix("Error").upper()
        _update(
            store,
            snapshot,
            state="failed",
            stage=None,
            error_code=code,
            message=str(exc)[:200],
        )
    except SoftTimeLimitExceeded:
        _update(
            store,
            snapshot,
            state="failed",
            stage=None,
            error_code="TIMEOUT",
            message="抓取任务超时",
        )
    except Exception:
        logger.exception("资源刮削任务失败: {}", avid)
        _update(
            store,
            snapshot,
            state="failed",
            stage=None,
            error_code="INTERNAL_ERROR",
            message="抓取任务失败",
        )
    finally:
        try:
            final_snapshot = store.get(task_id)
            logger.info(
                "scrape_job source={} task_id={} state={} queue_wait_ms={} scrape_total_ms={}",
                source if source in {"jable", "missav", "any"} else "other",
                task_id,
                final_snapshot.get("state", "unknown") if final_snapshot else "unknown",
                queue_wait_ms,
                round((time.monotonic() - scrape_started) * 1000),
            )
        finally:
            store.release(avid, task_id)
