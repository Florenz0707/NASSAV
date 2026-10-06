from types import SimpleNamespace

import pytest
from nassav import resource_job_details as details


@pytest.mark.parametrize(
    "state,result,expected",
    [
        ("PENDING", None, "queued"),
        ("STARTED", None, "translating"),
        ("SUCCESS", {"success": True, "translation_status": "completed"}, "completed"),
        ("SUCCESS", {"success": False, "translation_status": "failed"}, "failed"),
        ("SUCCESS", {"success": False, "translation_status": "skipped"}, "skipped"),
        ("SUCCESS", None, "failed"),
        ("FAILURE", RuntimeError("private"), "failed"),
    ],
)
def test_translation_uses_business_result(monkeypatch, state, result, expected):
    monkeypatch.setattr(
        details,
        "AsyncResult",
        lambda task_id: SimpleNamespace(state=state, result=result),
    )
    actual = details.translation_details("child")
    assert actual["state"] == expected
    assert "private" not in str(actual)


def test_result_backend_failure_is_retryable_unknown(monkeypatch):
    def unavailable(task_id):
        raise RuntimeError("redis down")

    monkeypatch.setattr(details, "AsyncResult", unavailable)
    assert details.translation_details("child")["state"] == "unknown"


@pytest.mark.django_db
def test_job_details_include_saved_names_without_changing_parent(
    resource_factory, monkeypatch
):
    resource_factory(
        avid="TITLE-1", source_title="Source", translated_title="Translated"
    )
    monkeypatch.setattr(
        details,
        "translation_details",
        lambda task_id: {"task_id": task_id, "state": "failed"},
    )
    snapshot = {
        "task_id": "parent",
        "avid": "TITLE-1",
        "state": "succeeded",
        "version": 7,
        "translation": {"task_id": "child", "state": "queued"},
    }
    result = details.resource_job_details(snapshot)
    assert result["state"] == "succeeded" and result["version"] == 7
    assert result["resource"]["source_title"] == "Source"
    assert result["translation"]["state"] == "failed"
    assert snapshot["translation"]["state"] == "queued"


@pytest.mark.parametrize(
    "child,expected_state,expected_stage",
    [
        ("queued", "running", "translation_queued"),
        ("translating", "running", "translation_translating"),
        ("completed", "succeeded", "translation_completed"),
        ("failed", "failed", "translation_failed"),
        ("skipped", "succeeded", "translation_skipped"),
    ],
)
@pytest.mark.django_db
def test_workflow_includes_translation_without_changing_persistence_state(
    monkeypatch, child, expected_state, expected_stage
):
    monkeypatch.setattr(
        details,
        "translation_details",
        lambda _: {
            "task_id": "child",
            "state": child,
            "completed_at": "2026-10-06T10:00:00+00:00",
        },
    )
    snapshot = {
        "avid": "ABSENT",
        "state": "succeeded",
        "version": 5,
        "translation": {"task_id": "child"},
        "timeline": [{"stage": "saving", "at": 10}],
    }
    result = details.resource_job_details(snapshot)
    assert (result["workflow_state"], result["workflow_stage"]) == (
        expected_state,
        expected_stage,
    )
    assert result["state"] == "succeeded" and result["version"] == 5
    assert snapshot["timeline"] == [{"stage": "saving", "at": 10}]
    if child in {"completed", "failed", "skipped"}:
        assert result["timeline"][-1]["at"] == "2026-10-06T10:00:00+00:00"


def test_translation_completion_uses_celery_completion_time(monkeypatch):
    from datetime import datetime, timezone

    completed = datetime(2026, 10, 6, 10, tzinfo=timezone.utc)
    monkeypatch.setattr(
        details,
        "AsyncResult",
        lambda _: SimpleNamespace(
            state="SUCCESS",
            result={"success": True, "translation_status": "completed"},
            date_done=completed,
        ),
    )
    assert details.translation_details("child")["completed_at"] == completed.isoformat()
