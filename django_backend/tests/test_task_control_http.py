"""Commands remain authorized, versioned and independent of broker availability."""

from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model

from nassav.task_records import DjangoTaskRecords
from nassav.task_models import TaskJob


@pytest.fixture
def task(db, operator_user):
    user = operator_user
    records = DjangoTaskRecords()
    job, _ = records.create(
        "download", "CONTROL-1", owner_id=user.pk, action="download"
    )
    return records, job


def test_pause_and_cancel_queue_are_versioned_idempotent(api_client, task):
    records, job = task
    path = f"/nassav/api/tasks/jobs/{job['job_id']}"
    request_id = str(uuid4())
    payload = {"request_id": request_id, "expected_version": job["version"]}
    paused = api_client.post(path + "/pause", payload, format="json")
    assert paused.status_code == 202
    assert paused.json()["data"]["state"] == "paused"
    assert (
        api_client.post(path + "/pause", payload, format="json").json()["data"][
            "version"
        ]
        == paused.json()["data"]["version"]
    )
    conflict = api_client.post(
        path + "/cancel", {**payload, "request_id": str(uuid4())}, format="json"
    )
    assert conflict.status_code == 409
    current = records.get(job["job_id"])
    cancelled = api_client.post(
        path + "/cancel",
        {"request_id": str(uuid4()), "expected_version": current["version"]},
        format="json",
    )
    assert cancelled.status_code == 202
    assert cancelled.json()["data"]["state"] == "cancelled"


def test_public_snapshot_does_not_expose_media_url_key_or_files(api_client, task):
    _, job = task
    TaskJob.objects.filter(pk=job["job_id"]).update(
        checkpoint={
            "download": {"url": "secret", "key": "secret"},
            "path": "private",
            "progress": {"percent": 20},
        }
    )
    response = api_client.get(f"/nassav/api/tasks/jobs/{job['job_id']}")
    assert response.status_code == 200
    assert "secret" not in response.content.decode()
    assert "checkpoint" not in response.json()["data"]
    assert response.json()["data"]["progress"]["percent"] == 20


def test_other_user_and_anonymous_cannot_control_or_read(api_client, task):
    _, job = task
    other = get_user_model().objects.create_user(username="other-task-user")
    api_client.force_authenticate(other)
    path = f"/nassav/api/tasks/jobs/{job['job_id']}"
    assert api_client.get(path).status_code == 403
    assert (
        api_client.post(
            path + "/pause",
            {"request_id": str(uuid4()), "expected_version": job["version"]},
            format="json",
        ).status_code
        == 403
    )
    api_client.force_authenticate(None)
    api_client.logout()
    assert api_client.get(path).status_code == 401


@pytest.mark.parametrize(
    "payload",
    [{}, {"expected_version": True}, {"expected_version": 1, "request_id": "invalid"}],
)
def test_malformed_controls_are_rejected(api_client, task, payload):
    _, job = task
    assert (
        api_client.post(
            f"/nassav/api/tasks/jobs/{job['job_id']}/pause", payload, format="json"
        ).status_code
        == 400
    )


def test_submission_keeps_attempt_pending_when_broker_fails(
    api_client, resource_factory, monkeypatch
):
    from nassav.tasks import download_video_task
    from nassav import download_queue

    resource_factory(avid="BROKER-1")

    def fail(*args, **kwargs):
        raise RuntimeError("broker unavailable")

    monkeypatch.setattr(download_video_task, "apply_async", fail)
    monkeypatch.setattr(
        download_queue, "add_task_to_queue", lambda *args, **kwargs: None
    )
    response = api_client.post("/nassav/api/downloads/BROKER-1")
    assert response.status_code == 202
    data = response.json()["data"]
    assert data["job_id"]
    job = TaskJob.objects.get(pk=data["job_id"])
    attempt = job.attempts.get()
    assert attempt.state == "pending"
    assert attempt.dispatch_error == "broker unavailable"


def test_list_is_owner_filtered_and_batch_returns_partial_results(
    api_client, task, operator_user
):
    records, job = task
    other = get_user_model().objects.create_user(username="batch-other")
    foreign, _ = records.create("scrape", "PRIVATE-1", owner_id=other.pk, action="add")
    second, _ = records.create(
        "scrape", "OWN-2", owner_id=operator_user.pk, action="add"
    )
    response = api_client.get("/nassav/api/tasks/jobs?page_size=1")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["pagination"] == {
        "page": 1,
        "page_size": 1,
        "total": 2,
        "has_more": True,
    }
    assert "PRIVATE-1" not in response.content.decode()
    request_id = str(uuid4())
    payload = {
        "action": "pause",
        "request_id": request_id,
        "items": [
            {"job_id": job["job_id"], "expected_version": job["version"]},
            {"job_id": second["job_id"], "expected_version": second["version"] + 1},
            {"job_id": foreign["job_id"], "expected_version": foreign["version"]},
        ],
    }
    response = api_client.post("/nassav/api/tasks/jobs/actions", payload, format="json")
    results = response.json()["data"]["results"]
    assert [r["code"] for r in results] == [202, 409, 403]
    assert results[0]["job"]["state"] == "paused"
    assert results[2]["job"] is None
    retried = api_client.post("/nassav/api/tasks/jobs/actions", payload, format="json")
    assert (
        retried.json()["data"]["results"][0]["job"]["version"]
        == results[0]["job"]["version"]
    )
    assert records.get(second["job_id"])["state"] == "queued"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"action": "cancel", "request_id": str(uuid4()), "items": []},
        {
            "action": "pause",
            "request_id": str(uuid4()),
            "items": [{"job_id": "invalid"}],
        },
    ],
)
def test_invalid_batches_are_rejected(api_client, payload):
    assert (
        api_client.post(
            "/nassav/api/tasks/jobs/actions", payload, format="json"
        ).status_code
        == 400
    )
