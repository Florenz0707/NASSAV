"""Browser result reuse never outlives configured policy or Redis retention."""

from nassav.search_job_views import public_snapshot
from nassav.scrape_jobs import SNAPSHOT_TTL


def test_result_cache_lifetime_is_remaining_not_a_sliding_window(settings, monkeypatch):
    settings.SOURCE_CREDENTIALS_ENABLED = False
    settings.EXTERNAL_SEARCH_RESULT_TTL_SECONDS = 60
    monkeypatch.setattr("time.time", lambda: 120)
    snapshot = {"state": "succeeded", "completed_at": 100, "updated_at": 110}
    assert public_snapshot(snapshot)["result_cache_ttl_seconds"] == 40
    settings.EXTERNAL_SEARCH_RESULT_TTL_SECONDS = 10
    assert public_snapshot(snapshot)["result_cache_ttl_seconds"] == 0
    settings.EXTERNAL_SEARCH_RESULT_TTL_SECONDS = 0
    assert public_snapshot(snapshot)["result_cache_ttl_seconds"] == 0
    settings.EXTERNAL_SEARCH_RESULT_TTL_SECONDS = 864000
    assert (
        public_snapshot(snapshot)["result_cache_ttl_seconds"]
        == 110 + SNAPSHOT_TTL - 120
    )
    for state in ["running", "failed", "cancelled"]:
        assert (
            public_snapshot({**snapshot, "state": state})["result_cache_ttl_seconds"]
            == 0
        )
