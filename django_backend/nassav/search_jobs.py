"""Bounded external searches, with query ownership and expiring Redis snapshots."""

import hashlib
import json
import math
import time
from uuid import uuid4

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from django.conf import settings
from django.core import signing
from loguru import logger

from nassav.external_search import (
    ExternalSearchResult,
    external_search_service,
    paginate_results,
)
from nassav.models import Actor, Genre
from nassav.scrape_jobs import JobStore, RedisJobStore
from nassav.source.search_contracts import SourceSearchError, SourceSearchUnavailable

JOB_DEADLINE = 1800
_RETAIN_RESULT_LOCK = "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('expire', KEYS[1], ARGV[2]) else return 0 end"


class SearchJobCancelled(Exception):
    """A worker observed a persisted cancellation between upstream pages."""


class SearchJobAlreadyFinished(Exception):
    """Cancellation lost the race to a terminal snapshot."""


class RedisSearchJobStore(RedisJobStore):
    """Keep search snapshots and locks separate from resource jobs."""

    @staticmethod
    def _lock_key(avid: str) -> str:
        return f"nassav:search:lock:{avid}"

    @staticmethod
    def _status_key(task_id: str) -> str:
        return f"nassav:search:job:{task_id}"

    def save(self, snapshot: dict) -> dict:
        current = super().save(snapshot)
        if current["state"] == "succeeded":
            # Keep the query owner for the configured reuse window, including windows > 4h.
            remaining = max(
                1,
                math.ceil(
                    current["completed_at"]
                    + settings.EXTERNAL_SEARCH_RESULT_TTL_SECONDS
                    - time.time()
                ),
            )
            self.client.eval(
                _RETAIN_RESULT_LOCK,
                1,
                self._lock_key(current["query_key"]),
                current["task_id"],
                remaining,
            )
        return current


def search_job_token(task_id: str) -> str:
    return signing.dumps(task_id, salt="nassav.search.job")


def valid_search_job_token(task_id: str, token: str) -> bool:
    try:
        return (
            signing.loads(
                token,
                salt="nassav.search.job",
                max_age=max(
                    86400, JOB_DEADLINE + settings.EXTERNAL_SEARCH_RESULT_TTL_SECONDS
                ),
            )
            == task_id
        )
    except signing.BadSignature:
        return False


def validate_search_query(query: dict) -> dict:
    """Resolve defaults and validate without fetching an upstream page."""
    entity = query.get("entity_type")
    if entity not in {"actor", "genre"}:
        raise ValueError("搜索类型必须是 actor 或 genre")
    entity_id = int(query["entity_id"])
    model = Actor if entity == "actor" else Genre
    if not model.objects.filter(pk=entity_id).exists():
        raise model.DoesNotExist
    capability_rows = external_search_service.capabilities()
    source = str(query.get("source") or "").strip().lower()
    if not source:
        source = external_search_service.default_source(entity)
    if source not in external_search_service.registered_sources():
        if not source:
            raise SourceSearchUnavailable("source_disabled")
        raise ValueError("搜索源无效")
    capability = next(
        (
            entry
            for entry in capability_rows
            if entry["source"] == source and entry[entity]
        ),
        None,
    )
    if capability is None:
        raise SourceSearchUnavailable("source_disabled")
    ordering = str(query.get("ordering") or "-views")
    if ordering not in capability["orderings"]:
        raise ValueError("搜索排序无效")
    page = int(query.get("page", 1))
    page_size = int(query.get("page_size", 20))
    if page < 1 or not 1 <= page_size <= 100:
        raise ValueError("分页参数无效")
    force_refresh = query.get("force_refresh", False)
    if not isinstance(force_refresh, bool):
        raise ValueError("force_refresh 必须是布尔值")
    return dict(
        entity_type=entity,
        entity_id=entity_id,
        source=source,
        ordering=ordering,
        page=page,
        page_size=page_size,
        force_refresh=force_refresh,
    )


def _query_key(query: dict) -> str:
    domain, route = external_search_service.cache_context(query["source"])
    context = {
        "query": query,
        "language": "cn-v4",
        "domain": domain,
        "route": None if route == "direct" else route,
        "fetch_pages": getattr(settings, "EXTERNAL_SEARCH_FETCH_PAGES", 5),
    }
    return hashlib.sha256(json.dumps(context, sort_keys=True).encode()).hexdigest()


def _publish(snapshot: dict) -> None:
    from nassav.consumers import send_task_update

    # Global socket only carries routing/version; results need the signed API token.
    event = {
        key: snapshot[key] for key in ("task_id", "state", "version", "updated_at")
    }
    try:
        send_task_update("external_search_update", event)
    except Exception:
        logger.warning(
            "外部搜索推送失败 task_id={}，可通过快照恢复", snapshot["task_id"]
        )


def _save(store: JobStore, snapshot: dict) -> dict:
    current = store.save(snapshot)
    _publish(current)
    return current


def _result_payload(result: ExternalSearchResult, query: dict) -> dict:
    return {
        "data": {
            "detail": result.meta.get(query["entity_type"]),
            "external_source": query["source"],
            "external_meta": result.meta,
            "external_results": result.items,
        },
        "pagination": result.pagination,
    }


def submit_search_job(
    query: dict, *, store: JobStore | None = None
) -> tuple[dict, bool]:
    query = validate_search_query(query)
    store = store or RedisSearchJobStore()
    key = _query_key(query)
    task_id = str(uuid4())
    owner = store.acquire(key, task_id)
    if owner is not None:
        existing = get_search_job(owner, store=store) if owner else None
        if existing and existing["state"] not in {"failed", "cancelled"}:
            # Forced requests only reuse work that is still running.
            ttl = settings.EXTERNAL_SEARCH_RESULT_TTL_SECONDS
            fresh = ttl > 0 and existing.get("completed_at", 0) + ttl > time.time()
            if existing["state"] in {"queued", "running"} or (
                fresh and not query["force_refresh"]
            ):
                return existing, True
        if owner:
            store.release(key, owner)
        if store.acquire(key, task_id) is not None:
            raise RuntimeError("搜索正在提交，请重试")
    snapshot = dict(
        task_id=task_id,
        job_type="external_search",
        query=query,
        query_key=key,
        state="queued",
        submitted_at=time.time(),
        result=None,
        pages_completed=0,
        error_code=None,
        message=None,
    )
    try:
        snapshot = _save(store, snapshot)
        run_search_job.apply_async(
            args=(task_id,), task_id=task_id, queue="scrape", expires=JOB_DEADLINE
        )
    except Exception:
        store.delete(task_id)
        store.release(key, task_id)
        raise
    return snapshot, False


def get_search_job(
    task_id: str,
    *,
    page: int | None = None,
    page_size: int | None = None,
    store: JobStore | None = None,
) -> dict | None:
    store = store or RedisSearchJobStore()
    snapshot = store.get(task_id)
    if (
        snapshot
        and snapshot["state"] in {"queued", "running"}
        and time.time() - snapshot["submitted_at"] > JOB_DEADLINE
    ):
        snapshot = _save(
            store,
            {
                **snapshot,
                "state": "failed",
                "error_code": "TIMEOUT",
                "message": "搜索任务已超时，请重试",
            },
        )
        store.release(snapshot["query_key"], task_id)
    if snapshot and page is not None and snapshot.get("result"):
        if page < 1 or page_size is None or not 1 <= page_size <= 100:
            raise ValueError("分页参数无效")
        items = snapshot.get("collected_results")
        if items is None:
            original = snapshot["result"]["pagination"]
            if page == original["page"] and page_size == original.get("page_size", 20):
                return snapshot
            raise ValueError("旧任务不支持跨页浏览，请重新搜索")
        visible, pagination = paginate_results(items, page=page, page_size=page_size)
        payload = snapshot["result"]
        snapshot = {
            **snapshot,
            "result": {
                **payload,
                "data": {**payload["data"], "external_results": visible},
                "pagination": pagination,
            },
        }
    return snapshot


def cancel_search_job(task_id: str, *, store: JobStore | None = None) -> dict | None:
    """Persist cancellation before revoking delivery; the worker checks between pages."""
    store = store or RedisSearchJobStore()
    snapshot = get_search_job(task_id, store=store)
    if snapshot is None or snapshot["state"] == "cancelled":
        return snapshot
    if snapshot["state"] in {"succeeded", "failed"}:
        raise SearchJobAlreadyFinished
    cancelled = _save(
        store,
        {
            **snapshot,
            "state": "cancelled",
            "error_code": "CANCELLED",
            "message": "搜索已取消",
            "completed_at": time.time(),
        },
    )
    if cancelled["state"] != "cancelled":
        raise SearchJobAlreadyFinished
    store.release(cancelled["query_key"], task_id)
    try:
        run_search_job.app.control.revoke(task_id)
    except Exception:
        # The snapshot is authoritative even if the broker cannot revoke delivery.
        logger.warning("搜索任务已取消，但队列撤销通知失败 task_id={}", task_id)
    return cancelled


def execute_search_job(task_id: str, *, store: JobStore | None = None) -> dict | None:
    store = store or RedisSearchJobStore()
    initial = get_search_job(task_id, store=store)
    if not initial or initial["state"] not in {"queued", "running"}:
        return initial
    snapshot: dict = initial
    if not store.renew(snapshot["query_key"], task_id):
        return _save(
            store,
            {
                **snapshot,
                "state": "failed",
                "error_code": "WORKER_LOST",
                "message": "搜索任务已过期，请重试",
            },
        )
    snapshot = _save(store, {**snapshot, "state": "running"})
    if snapshot["state"] != "running":
        return snapshot
    query = snapshot["query"]

    def ensure_active() -> None:
        current = store.get(task_id)
        if current is None or current["state"] == "cancelled":
            raise SearchJobCancelled
        if not store.renew(snapshot["query_key"], task_id):
            raise RuntimeError("搜索任务所有权已失效")

    def progress(result: ExternalSearchResult) -> None:
        nonlocal snapshot
        ensure_active()
        snapshot = _save(
            store,
            {
                **snapshot,
                "state": "running",
                "pages_completed": result.meta["pages_completed"],
                "result": _result_payload(result, query),
                "collected_results": result.collected_items
                if result.collected_items is not None
                else result.items,
            },
        )
        if snapshot["state"] != "running":
            raise RuntimeError("搜索任务已结束")

    try:
        entity = query["entity_type"]
        method = getattr(external_search_service, f"search_{entity}_detail")
        result = method(
            **{f"{entity}_id": query["entity_id"]},
            source_name=query["source"],
            page=query["page"],
            page_size=query["page_size"],
            ordering=query["ordering"],
            force_refresh=query["force_refresh"],
            on_progress=progress,
            should_cancel=ensure_active,
        )
        ensure_active()
        payload = _result_payload(result, query)
        return _save(
            store,
            {
                **snapshot,
                "state": "succeeded",
                "result": payload,
                "collected_results": result.collected_items
                if result.collected_items is not None
                else result.items,
                "completed_at": time.time(),
            },
        )
    except SearchJobCancelled:
        return store.get(task_id)
    except SoftTimeLimitExceeded:
        code, message = "TIMEOUT", "搜索任务超时，请重试"
    except (SourceSearchError, SourceSearchUnavailable):
        code, message = "SOURCE_FETCH_FAILED", "外部源搜索失败，请稍后重试"
    except (Actor.DoesNotExist, Genre.DoesNotExist):
        code, message = "ENTITY_NOT_FOUND", "搜索对象已不存在"
    except Exception:
        logger.exception("外部搜索任务失败 task_id={}", task_id)
        code, message = "INTERNAL_ERROR", "搜索失败，请稍后重试"
    store.release(snapshot["query_key"], task_id)
    return _save(
        store, {**snapshot, "state": "failed", "error_code": code, "message": message}
    )


@shared_task(
    name="nassav.search_jobs.run_search_job",
    soft_time_limit=900,
    time_limit=930,
    ignore_result=True,
)
def run_search_job(task_id: str):
    execute_search_job(task_id)
