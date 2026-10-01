"""Bounded external searches, with query ownership and expiring Redis snapshots."""

import hashlib
import json
import time
from uuid import uuid4

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from django.conf import settings
from django.core import signing
from loguru import logger

from nassav.external_search import external_search_service
from nassav.models import Actor, Genre
from nassav.scrape_jobs import JobStore, RedisJobStore
from nassav.source.search_contracts import SourceSearchError, SourceSearchUnavailable
from nassav.source.SourceManager import source_manager
from nassav.source.CookieRepository import proxy_route_profile

JOB_DEADLINE = 1800
RESULT_TTL = 300


class RedisSearchJobStore(RedisJobStore):
    """Keep search snapshots and locks separate from resource jobs."""

    @staticmethod
    def _lock_key(avid: str) -> str:
        return f"nassav:search:lock:{avid}"

    @staticmethod
    def _status_key(task_id: str) -> str:
        return f"nassav:search:job:{task_id}"


def search_job_token(task_id: str) -> str:
    return signing.dumps(task_id, salt="nassav.search.job")


def valid_search_job_token(task_id: str, token: str) -> bool:
    try:
        return signing.loads(token, salt="nassav.search.job", max_age=86400) == task_id
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
    if source not in {"jable", "missav"}:
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
    source = next(
        item
        for item in source_manager.sources.values()
        if item.get_source_name().lower() == query["source"]
    )
    context = {
        "query": query,
        "language": "cn-v4",
        "domain": source.domain,
        "route": proxy_route_profile(getattr(source, "proxy", None)),
        "fetch_pages": getattr(settings, "EXTERNAL_SEARCH_FETCH_PAGES", 5),
    }
    return hashlib.sha256(json.dumps(context, sort_keys=True).encode()).hexdigest()


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
        if existing and existing["state"] != "failed":
            # Forced requests only reuse work that is still running.
            fresh = existing.get("completed_at", 0) + RESULT_TTL > time.time()
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
        error_code=None,
        message=None,
    )
    try:
        snapshot = store.save(snapshot)
        run_search_job.apply_async(
            args=(task_id,), task_id=task_id, queue="scrape", expires=JOB_DEADLINE
        )
    except Exception:
        store.delete(task_id)
        store.release(key, task_id)
        raise
    return snapshot, False


def get_search_job(task_id: str, *, store: JobStore | None = None) -> dict | None:
    store = store or RedisSearchJobStore()
    snapshot = store.get(task_id)
    if (
        snapshot
        and snapshot["state"] in {"queued", "running"}
        and time.time() - snapshot["submitted_at"] > JOB_DEADLINE
    ):
        snapshot = store.save(
            {
                **snapshot,
                "state": "failed",
                "error_code": "TIMEOUT",
                "message": "搜索任务已超时，请重试",
            }
        )
        store.release(snapshot["query_key"], task_id)
    return snapshot


def execute_search_job(task_id: str, *, store: JobStore | None = None) -> dict | None:
    store = store or RedisSearchJobStore()
    snapshot = get_search_job(task_id, store=store)
    if not snapshot or snapshot["state"] not in {"queued", "running"}:
        return snapshot
    if not store.renew(snapshot["query_key"], task_id):
        return store.save(
            {
                **snapshot,
                "state": "failed",
                "error_code": "WORKER_LOST",
                "message": "搜索任务已过期，请重试",
            }
        )
    snapshot = store.save({**snapshot, "state": "running"})
    query = snapshot["query"]
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
        )
        payload = {
            "data": {
                "detail": result.meta.get(entity),
                "external_source": query["source"],
                "external_meta": result.meta,
                "external_results": result.items,
            },
            "pagination": result.pagination,
        }
        return store.save(
            {
                **snapshot,
                "state": "succeeded",
                "result": payload,
                "completed_at": time.time(),
            }
        )
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
    return store.save(
        {**snapshot, "state": "failed", "error_code": code, "message": message}
    )


@shared_task(
    name="nassav.search_jobs.run_search_job",
    soft_time_limit=900,
    time_limit=930,
    ignore_result=True,
)
def run_search_job(task_id: str):
    execute_search_job(task_id)
