"""Run: uv run pytest tests/test_search_jobs.py -v (no network or production Redis)."""

import time
from unittest.mock import Mock

import pytest
from nassav import search_jobs
from nassav.external_search import ExternalSearchResult
from nassav.scrape_jobs import JobStore
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
        if existing and existing["state"] in {"succeeded", "failed", "cancelled"}:
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
    # Serial job protocol fixtures replace adapter methods, not real sources.
    for adapter in search_jobs.external_search_service.adapters.values():
        if hasattr(adapter, "source_scope"):
            monkeypatch.setattr(adapter, "source_scope", None)
    monkeypatch.setattr(search_jobs, "_publish", Mock())
    monkeypatch.setattr(search_jobs, "RedisSearchJobStore", lambda: store)
    enqueue = Mock()
    monkeypatch.setattr(search_jobs.run_search_job, "apply_async", enqueue)
    monkeypatch.setattr(search_jobs.run_search_job.app.control, "revoke", Mock())
    return store, enqueue


@pytest.mark.django_db
@pytest.mark.parametrize("source_fails", [False, True])
def test_empty_search_is_success_but_source_failure_is_visible(
    actor_factory, runtime, monkeypatch, source_fails
):
    method = Mock(
        return_value=ExternalSearchResult(items=[], pagination={"total": 0}, meta={}),
        side_effect=SourceSearchError("isolated failure") if source_fails else None,
    )
    monkeypatch.setattr(
        search_jobs.external_search_service, "search_actor_detail", method
    )
    job, _ = search_jobs.submit_search_job(
        {"entity_type": "actor", "entity_id": actor_factory().pk, "source": "jable"}
    )
    final = search_jobs.execute_search_job(job["task_id"])
    if source_fails:
        assert final["state"] == "failed"
        assert final["error_code"] == "SOURCE_FETCH_FAILED"
        assert final["result"] is None
    else:
        assert final["state"] == "succeeded"
        assert final["error_code"] is None
        assert final["result"]["data"]["external_results"] == []
        assert final["result"]["pagination"]["total"] == 0
    if source_fails:
        assert not runtime[0].locks
    else:
        # A successful query retains ownership for completed-result reuse.
        assert runtime[0].locks[job["query_key"]] == job["task_id"]
    method.assert_called_once()


@pytest.mark.django_db
def test_cancel_requires_token_releases_lock_and_allows_resubmit(
    actor_factory, api_client, runtime
):
    query = {"entity_type": "actor", "entity_id": actor_factory().pk, "source": "jable"}
    submitted = api_client.post("/nassav/api/search/jobs", query, format="json").json()[
        "data"
    ]
    task_id = submitted["task_id"]
    url = f"/nassav/api/search/jobs/{task_id}/cancel"
    assert api_client.post(url, {"token": "bad"}, format="json").status_code == 403
    response = api_client.post(url, {"token": submitted["token"]}, format="json")
    assert response.status_code == 200
    assert response.json()["data"]["state"] == "cancelled"
    assert "query_key" not in response.json()["data"]
    assert not runtime[0].locks
    assert search_jobs.execute_search_job(task_id)["state"] == "cancelled"
    assert (
        api_client.post(url, {"token": submitted["token"]}, format="json").status_code
        == 200
    )
    retry = api_client.post("/nassav/api/search/jobs", query, format="json").json()[
        "data"
    ]
    assert retry["task_id"] != task_id
    search_jobs.run_search_job.app.control.revoke.assert_called_with(task_id)


@pytest.mark.django_db
def test_running_cancel_stops_after_current_page_and_preserves_partial_result(
    actor_factory, runtime, settings, monkeypatch
):
    settings.EXTERNAL_SEARCH_FETCH_PAGES = 3
    settings.EXTERNAL_SEARCH_CACHE_ENABLED = False
    actor = actor_factory()
    job, _ = search_jobs.submit_search_job(
        {"entity_type": "actor", "entity_id": actor.pk, "source": "jable"}
    )
    fetched = []

    def fetch(**kwargs):
        fetched.append(kwargs["page"])
        if kwargs["page"] == 2:
            cancelled = search_jobs.cancel_search_job(job["task_id"])
            assert cancelled["pages_completed"] == 1
            assert cancelled["result"]["data"]["external_meta"]["partial"]
        return [{"avid": f"TEST-{kwargs['page']:03}", "metrics": {"views": 1}}]

    monkeypatch.setattr(
        search_jobs.external_search_service.adapters["jable"],
        "search_actor_items",
        Mock(side_effect=fetch),
    )
    final = search_jobs.execute_search_job(job["task_id"])
    assert final["state"] == "cancelled"
    assert fetched == [1, 2]
    assert final["pages_completed"] == 1
    assert not runtime[0].locks
    assert runtime[0].save({**final, "state": "succeeded"})["state"] == "cancelled"


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
    assert (
        api_client.post(
            f"{path}/cancel", {"token": job["token"]}, format="json"
        ).status_code
        == 409
    )
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
    actor_factory, api_client, runtime, settings, monkeypatch, operator_user
):
    from nassav.personal_preferences import update_preferences

    update_preferences(operator_user.pk, {"default_external_search_source": "missav"})
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


@pytest.mark.django_db
@pytest.mark.parametrize("entity", ["actor", "genre"])
@pytest.mark.parametrize("source", ["missav", "jable"])
@pytest.mark.parametrize("fail_last", [False, True])
def test_page_progress_is_visible_before_completion_and_failure_keeps_results(
    entity,
    source,
    fail_last,
    actor_factory,
    genre_factory,
    runtime,
    settings,
    monkeypatch,
):
    from django.core.cache import cache

    cache.clear()
    settings.EXTERNAL_SEARCH_FETCH_PAGES = 3
    settings.EXTERNAL_SEARCH_CACHE_ENABLED = True
    obj = actor_factory() if entity == "actor" else genre_factory()
    query = {"entity_type": entity, "entity_id": obj.pk, "source": source}
    job, _ = search_jobs.submit_search_job(query)
    store = runtime[0]
    seen = []

    def fetch(**kwargs):
        page = kwargs["page"]
        if page > 1:
            snapshot = store.get(job["task_id"])
            assert snapshot["state"] == "running"
            assert snapshot["pages_completed"] == page - 1
            assert snapshot["result"]["data"]["external_meta"]["partial"]
            expected = [f"TEST-{number:03}" for number in range(1, page)]
            if source == "jable":
                expected.reverse()
            assert [
                item["avid"] for item in snapshot["result"]["data"]["external_results"]
            ] == expected
            assert snapshot["result"]["pagination"]["total"] == page - 1
            assert len(snapshot["collected_results"]) == page - 1
            paged = search_jobs.get_search_job(
                job["task_id"], page=page - 1, page_size=1
            )
            assert paged["result"]["pagination"]["pages"] == page - 1
            assert len(paged["result"]["data"]["external_results"]) == 1
            seen.append(snapshot["version"])
        if page == 3 and fail_last:
            raise SourceSearchError("timeout")
        # Page two repeats an item: cumulative snapshots must deduplicate it.
        items = [{"avid": f"TEST-{page:03}", "metrics": {"views": page}}]
        if page == 2:
            items.append({"avid": "TEST-001", "metrics": {"views": 1}})
        return items

    method = Mock(side_effect=fetch)
    monkeypatch.setattr(
        search_jobs.external_search_service.adapters[source],
        f"search_{entity}_items",
        method,
    )
    final = search_jobs.execute_search_job(job["task_id"])
    assert seen == sorted(set(seen)) and len(seen) == 2
    assert final["version"] > seen[-1]
    assert final["state"] == ("failed" if fail_last else "succeeded")
    meta = final["result"]["data"]["external_meta"]
    assert meta["partial"] == fail_last
    assert len(final["result"]["data"]["external_results"]) == (2 if fail_last else 3)
    if fail_last:
        assert final["pages_completed"] == 2
        retry, _ = search_jobs.submit_search_job(query)
        assert retry["task_id"] != job["task_id"]
        # No successful search cache was populated by the first two pages.
        job = retry
        assert search_jobs.execute_search_job(retry["task_id"])["state"] == "failed"
        assert method.call_count == 6
    else:
        cached = getattr(
            search_jobs.external_search_service, f"search_{entity}_detail"
        )(
            **{f"{entity}_id": obj.pk},
            source_name=source,
            page=1,
            page_size=20,
            ordering="-views",
        )
        assert cached.meta["cache"]["hit"]
        assert method.call_count == 3
    cache.clear()


def test_search_notification_exposes_only_routing_version_and_survives_socket_failure(
    monkeypatch,
):
    publish = Mock()
    monkeypatch.setattr("nassav.consumers.send_task_update", publish)
    snapshot = {
        "task_id": "id",
        "state": "running",
        "version": 3,
        "updated_at": 10,
        "result": {"private": "cards"},
        "query": {"entity_id": 42},
        "token": "secret",
    }
    search_jobs._publish(snapshot)
    publish.assert_called_once_with(
        "external_search_update",
        {
            "task_id": "id",
            "state": "running",
            "version": 3,
            "updated_at": 10,
        },
    )
    publish.side_effect = RuntimeError("channel unavailable")
    assert search_jobs._publish(snapshot) is None


@pytest.mark.django_db
def test_late_page_cannot_revive_a_terminal_search(actor_factory, runtime, monkeypatch):
    query = {
        "entity_type": "actor",
        "entity_id": actor_factory().pk,
        "source": "missav",
    }
    job, _ = search_jobs.submit_search_job(query)
    store = runtime[0]

    def search(**kwargs):
        store.save(
            {**store.get(job["task_id"]), "state": "failed", "error_code": "TIMEOUT"}
        )
        kwargs["on_progress"](
            ExternalSearchResult(
                items=[{"avid": "LATE-001"}],
                pagination={},
                meta={"pages_completed": 1},
            )
        )

    monkeypatch.setattr(
        search_jobs.external_search_service, "search_actor_detail", search
    )
    final = search_jobs.execute_search_job(job["task_id"])
    assert final["state"] == "failed" and final["error_code"] == "TIMEOUT"
    assert final["result"] is None


@pytest.mark.parametrize("state", ["running", "succeeded", "failed", "cancelled"])
@pytest.mark.django_db
def test_read_other_pages_of_same_job_without_fetching_or_mutating(runtime, state):
    store, enqueue = runtime
    items = [{"avid": f"ITEM-{i}"} for i in range(31)]
    original = {
        "task_id": "paged-job",
        "state": state,
        "submitted_at": time.time(),
        "query": {"page": 1, "page_size": 15},
        "collected_results": items,
        "result": {
            "data": {
                "external_results": items[:15],
                "external_meta": {"partial": state != "succeeded"},
            },
            "pagination": {"page": 1, "page_size": 15, "pages": 3, "total": 31},
        },
    }
    store.rows["paged-job"] = original
    second = search_jobs.get_search_job("paged-job", page=2, page_size=15, store=store)
    assert second["result"]["data"]["external_results"] == [
        {**item, "in_library": False} for item in items[15:30]
    ]
    last = search_jobs.get_search_job("paged-job", page=3, page_size=15, store=store)
    assert last["result"]["data"]["external_results"] == [
        {**item, "in_library": False} for item in items[30:]
    ]
    assert last["result"]["pagination"] == {
        "page": 3,
        "page_size": 15,
        "pages": 3,
        "total": 31,
    }
    assert original["result"]["pagination"]["page"] == 1
    enqueue.assert_not_called()


@pytest.mark.django_db
def test_signed_status_pages_do_not_expose_internal_collection(
    actor_factory, api_client, runtime, operator_user
):
    actor = actor_factory()
    job, _ = search_jobs.submit_search_job(
        {"entity_type": "actor", "entity_id": actor.pk}, user_id=operator_user.pk
    )
    items = [{"avid": f"ITEM-{i}"} for i in range(31)]
    runtime[0].save(
        {
            **job,
            "state": "running",
            "collected_results": items,
            "result": {
                "data": {
                    "external_results": items[:15],
                    "external_meta": {"partial": True},
                },
                "pagination": {"page": 1, "page_size": 15, "pages": 3, "total": 31},
            },
        }
    )
    url = f"/nassav/api/search/jobs/{job['task_id']}"
    params = {
        "token": search_jobs.search_job_token(job["task_id"], user_id=operator_user.pk),
        "page": 2,
        "page_size": 15,
    }
    response = api_client.get(url, params)
    assert response.status_code == 200
    data = response.json()["data"]
    assert "collected_results" not in data
    assert "query_key" not in data
    assert data["result"]["data"]["external_results"] == [
        {**item, "in_library": False, "detail_cached": False} for item in items[15:30]
    ]
    assert api_client.get(url, {**params, "page": 0}).status_code == 400
    assert api_client.get(url, {**params, "token": "invalid"}).status_code == 403
    assert runtime[1].call_count == 1


@pytest.mark.django_db
@pytest.mark.parametrize(
    "ttl,age,reused",
    [(60, 59, True), (60, 60, False), (3600, 301, True), (0, 0, False)],
)
def test_completed_result_reuse_obeys_configured_ttl(
    actor_factory, runtime, settings, monkeypatch, ttl, age, reused
):
    settings.EXTERNAL_SEARCH_RESULT_TTL_SECONDS = ttl
    clock = [1000.0]
    monkeypatch.setattr(search_jobs.time, "time", lambda: clock[0])
    query = {"entity_type": "actor", "entity_id": actor_factory().pk, "source": "jable"}
    first, duplicate = search_jobs.submit_search_job(query)
    assert not duplicate
    # Even disabled completed-result reuse must retain in-flight deduplication.
    assert search_jobs.submit_search_job(query)[1]
    runtime[0].save({**first, "state": "succeeded", "completed_at": clock[0]})
    clock[0] += age
    second, duplicate = search_jobs.submit_search_job(query)
    assert duplicate is reused
    assert (second["task_id"] == first["task_id"]) is reused
    assert runtime[1].call_count == (1 if reused else 2)


@pytest.mark.django_db
@pytest.mark.parametrize("cancel_wins", [False, True])
def test_complete_result_cache_publication_follows_terminal_commit(
    actor_factory, runtime, monkeypatch, cancel_wins
):
    store = runtime[0]
    publish = Mock()
    result = ExternalSearchResult(
        items=[], pagination={}, meta={}, publish_cache=publish
    )
    monkeypatch.setattr(
        search_jobs.external_search_service,
        "search_actor_detail",
        Mock(return_value=result),
    )
    job, _ = search_jobs.submit_search_job(
        {"entity_type": "actor", "entity_id": actor_factory().pk, "source": "jable"}
    )
    original = store.save

    def save(snapshot):
        if cancel_wins and snapshot["state"] == "succeeded":
            original({**snapshot, "state": "cancelled"})
        return original(snapshot)

    monkeypatch.setattr(store, "save", save)
    finished = search_jobs.execute_search_job(job["task_id"])
    assert finished["state"] == ("cancelled" if cancel_wins else "succeeded")
    assert publish.call_count == (0 if cancel_wins else 1)


@pytest.mark.django_db
def test_reused_task_result_reprojects_library_without_mutating_snapshot(
    actor_factory, resource_factory, runtime, monkeypatch
):
    result = ExternalSearchResult(
        items=[{"avid": "EXIST-001", "in_library": False}], pagination={}, meta={}
    )
    monkeypatch.setattr(
        search_jobs.external_search_service,
        "search_actor_detail",
        Mock(return_value=result),
    )
    job, _ = search_jobs.submit_search_job(
        {"entity_type": "actor", "entity_id": actor_factory().pk, "source": "jable"}
    )
    search_jobs.execute_search_job(job["task_id"])
    saved = resource_factory(avid="EXIST-001")
    read = search_jobs.get_search_job(job["task_id"])
    assert read["result"]["data"]["external_results"][0]["in_library"]
    assert not runtime[0].rows[job["task_id"]]["result"]["data"]["external_results"][0][
        "in_library"
    ]
    saved.delete()
    assert not search_jobs.get_search_job(job["task_id"])["result"]["data"][
        "external_results"
    ][0]["in_library"]


@pytest.mark.django_db
def test_search_handles_and_tokens_are_owned_but_public_result_cache_can_be_shared(
    actor_factory, django_user_model, runtime
):
    first = django_user_model.objects.create_user(username="search-owner-a")
    second = django_user_model.objects.create_user(username="search-owner-b")
    query = {"entity_type": "actor", "entity_id": actor_factory().pk}
    a, _ = search_jobs.submit_search_job(query, user_id=first.pk)
    b, duplicate = search_jobs.submit_search_job(query, user_id=second.pk)
    assert not duplicate and a["task_id"] != b["task_id"]
    assert search_jobs.submit_search_job(query, user_id=first.pk)[1]
    token = search_jobs.search_job_token(a["task_id"], user_id=first.pk)
    assert search_jobs.valid_search_job_token(a["task_id"], token, user_id=first.pk)
    assert not search_jobs.valid_search_job_token(
        a["task_id"], token, user_id=second.pk
    )
    assert not search_jobs.valid_search_job_token(
        a["task_id"], search_jobs.search_job_token(a["task_id"]), user_id=first.pk
    )


@pytest.mark.django_db
def test_account_epoch_change_cancels_old_search_before_network(
    actor_factory, operator_user, runtime, monkeypatch
):
    from nassav.account_models import UserAccount

    account = UserAccount.objects.create(user=operator_user)
    job, _ = search_jobs.submit_search_job(
        {"entity_type": "actor", "entity_id": actor_factory().pk},
        user_id=operator_user.pk,
    )
    account.version += 1
    account.save()
    fetch = Mock()
    monkeypatch.setattr(
        search_jobs.external_search_service, "search_actor_detail", fetch
    )
    result = search_jobs.execute_search_job(job["task_id"])
    assert result["state"] == "cancelled"
    fetch.assert_not_called()
