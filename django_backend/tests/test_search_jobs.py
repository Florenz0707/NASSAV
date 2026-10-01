"""Run: uv run pytest tests/test_search_jobs.py -v (no network or production Redis)."""

import time
from unittest.mock import Mock

import pytest
from nassav import search_jobs
from nassav.scrape_jobs import JobStore
from nassav.external_search import ExternalSearchResult
from nassav.source.search_contracts import SourceSearchError


class MemoryStore(JobStore):
    def __init__(self):
        self.locks = {}
        self.rows = {}

    def acquire(self, avid, task_id):
        owner = self.locks.get(avid)
        if owner is None:
            self.locks[avid] = task_id
        return owner

    def release(self, avid, task_id):
        if self.locks.get(avid) == task_id:
            self.locks.pop(avid)

    def renew(self, avid, task_id):
        return self.locks.get(avid) == task_id

    def get(self, task_id):
        return self.rows.get(task_id)

    def save(self, snapshot):
        existing = self.get(snapshot["task_id"])
        if existing and existing["state"] in {"succeeded", "failed"}:
            return existing
        value = {
            **snapshot,
            "version": (existing or {}).get("version", 0) + 1,
            "updated_at": time.time(),
        }
        self.rows[snapshot["task_id"]] = value
        return value

    def delete(self, task_id):
        self.rows.pop(task_id, None)


@pytest.fixture
def runtime(monkeypatch):
    store = MemoryStore()
    monkeypatch.setattr(search_jobs, "RedisSearchJobStore", lambda: store)
    enqueue = Mock()
    monkeypatch.setattr(search_jobs.run_search_job, "apply_async", enqueue)
    return store, enqueue


@pytest.mark.django_db
@pytest.mark.parametrize("entity", ["actor", "genre"])
def test_api_submission_worker_poll_and_completed_reuse(
    entity, actor_factory, genre_factory, api_client, runtime, monkeypatch
):
    obj = actor_factory() if entity == "actor" else genre_factory()
    query = {"entity_type": entity, "entity_id": obj.pk, "source": "missav"}
    method = Mock(
        return_value=ExternalSearchResult(
            items=[{"avid": "TEST-123"}],
            pagination={"page": 1},
            meta={entity: {"id": obj.pk}},
        )
    )
    monkeypatch.setattr(
        search_jobs.external_search_service, f"search_{entity}_detail", method
    )
    submit = api_client.post("/nassav/api/search/jobs", query, format="json")
    assert submit.status_code == 202
    job = submit.json()["data"]
    method.assert_not_called()
    duplicate = api_client.post("/nassav/api/search/jobs", query, format="json").json()[
        "data"
    ]
    assert duplicate["task_id"] == job["task_id"] and duplicate["duplicate"]
    assert runtime[1].call_count == 1
    path = f"/nassav/api/search/jobs/{job['task_id']}"
    assert api_client.get(path).status_code == 403
    assert (
        api_client.get(path, {"token": job["token"]}).json()["data"]["state"]
        == "queued"
    )
    result = search_jobs.execute_search_job(job["task_id"])
    assert result["state"] == "succeeded"
    polled = api_client.get(path, {"token": job["token"]}).json()["data"]
    assert polled["result"]["data"]["external_results"][0]["avid"] == "TEST-123"
    assert "query_key" not in polled
    assert (
        api_client.post("/nassav/api/search/jobs", query, format="json").json()["data"][
            "task_id"
        ]
        == job["task_id"]
    )
    method.assert_called_once()


@pytest.mark.django_db
def test_failure_timeout_retry_and_enqueue_cleanup(actor_factory, runtime, monkeypatch):
    query = {
        "entity_type": "actor",
        "entity_id": actor_factory().pk,
        "source": "missav",
    }
    monkeypatch.setattr(
        search_jobs.external_search_service,
        "search_actor_detail",
        Mock(side_effect=SourceSearchError("timeout")),
    )
    job, _ = search_jobs.submit_search_job(query)
    assert search_jobs.execute_search_job(job["task_id"])["state"] == "failed"
    retry, _ = search_jobs.submit_search_job(query)
    assert retry["task_id"] != job["task_id"]
    runtime[0].rows[retry["task_id"]]["submitted_at"] = (
        time.time() - search_jobs.JOB_DEADLINE - 1
    )
    assert search_jobs.get_search_job(retry["task_id"])["error_code"] == "TIMEOUT"
    assert not runtime[0].locks
    runtime[1].side_effect = RuntimeError("broker down")
    with pytest.raises(RuntimeError):
        search_jobs.submit_search_job(query)
    assert not runtime[0].locks


@pytest.mark.django_db
def test_forced_refresh_and_sources_are_isolated(actor_factory, runtime, monkeypatch):
    query = {
        "entity_type": "actor",
        "entity_id": actor_factory().pk,
        "source": "missav",
        "force_refresh": True,
    }
    monkeypatch.setattr(
        search_jobs.external_search_service,
        "search_actor_detail",
        Mock(return_value=ExternalSearchResult(items=[], pagination={}, meta={})),
    )
    first, _ = search_jobs.submit_search_job(query)
    assert search_jobs.submit_search_job(query)[0]["task_id"] == first["task_id"]
    search_jobs.execute_search_job(first["task_id"])
    assert search_jobs.submit_search_job(query)[0]["task_id"] != first["task_id"]
    other, _ = search_jobs.submit_search_job({**query, "source": "jable"})
    assert other["query_key"] != first["query_key"]


@pytest.mark.django_db
def test_validation_and_persisted_default(
    actor_factory, api_client, runtime, settings, monkeypatch
):
    from nassav.user_settings import get_settings_manager

    get_settings_manager().set("default_external_search_source", "missav")
    query = {"entity_type": "actor", "entity_id": actor_factory().pk}
    assert (
        api_client.post("/nassav/api/search/jobs", query, format="json").json()["data"][
            "query"
        ]["source"]
        == "missav"
    )
    for change in (
        {"source": "unknown"},
        {"page_size": 101},
        {"ordering": "views", "source": "missav"},
    ):
        assert (
            api_client.post(
                "/nassav/api/search/jobs", {**query, **change}, format="json"
            ).status_code
            == 400
        )
    monkeypatch.setattr(
        search_jobs.external_search_service,
        "capabilities",
        lambda: [
            {"source": "jable", "actor": True, "genre": True, "orderings": ["-views"]}
        ],
    )
    assert search_jobs.validate_search_query(query)["source"] == "jable"
    assert (
        api_client.post(
            "/nassav/api/search/jobs", {**query, "source": "missav"}, format="json"
        ).status_code
        == 503
    )
