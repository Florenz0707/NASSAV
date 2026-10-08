"""Result reuse TTL must work beyond the original query lock lifetime."""

import time
from nassav import search_jobs
from test_session_lifecycle_contracts import isolated_redis as isolated_redis


def test_completed_result_owner_retention_matches_ttl_without_touching_successor(
    isolated_redis, settings, monkeypatch
):
    settings.EXTERNAL_SEARCH_RESULT_TTL_SECONDS = 36000
    store = search_jobs.RedisSearchJobStore.__new__(search_jobs.RedisSearchJobStore)
    store.client = isolated_redis
    assert store.acquire("query", "old") is None
    completed = time.time() - 30
    snapshot = store.save(
        {
            "task_id": "old",
            "query_key": "query",
            "state": "succeeded",
            "completed_at": completed,
        }
    )
    lock = store._lock_key("query")
    assert 35960 <= isolated_redis.ttl(lock) <= 35970
    # A terminal late save must retain its original completion time.
    store.save({**snapshot, "completed_at": time.time()})
    assert 35960 <= isolated_redis.ttl(lock) <= 35970
    isolated_redis.set(lock, "successor", ex=123)
    store.save(snapshot)
    assert isolated_redis.get(lock) == b"successor"
    assert 120 <= isolated_redis.ttl(lock) <= 123


def test_one_day_result_window_remains_authorized_after_full_execution_budget(
    settings, monkeypatch
):
    settings.EXTERNAL_SEARCH_RESULT_TTL_SECONDS = 86400
    clock = [1000.0]
    monkeypatch.setattr(search_jobs.time, "time", lambda: clock[0])
    token = search_jobs.search_job_token("job")
    clock[0] += 86400 + search_jobs.JOB_DEADLINE - 1
    assert search_jobs.valid_search_job_token("job", token)
    clock[0] += 2
    assert not search_jobs.valid_search_job_token("job", token)
