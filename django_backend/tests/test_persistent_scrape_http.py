"""Production scrape submission keeps durable identity and owner-bound controls."""

from uuid import uuid4
from unittest.mock import Mock

import pytest

from nassav import scrape_jobs
from nassav.models import AVResource
from nassav.task_models import TaskAttempt, TaskJob


@pytest.mark.django_db
def test_http_submission_persists_owner_before_broker_and_supports_pause(
    api_client, operator_user, monkeypatch
):
    send = Mock(side_effect=ConnectionError("broker unavailable"))
    monkeypatch.setattr(scrape_jobs.run_resource_job, "apply_async", send)
    response = api_client.post(
        "/nassav/api/resource/jobs",
        {"action": "add", "avid": "PERSIST-1"},
        format="json",
    )
    assert response.status_code == 202
    data = response.json()["data"]
    job = TaskJob.objects.get(pk=data["job_id"])
    assert job.owner_id == operator_user.pk
    assert job.state == "queued"
    assert TaskAttempt.objects.get(job=job).state == "pending"
    assert "checkpoint" not in data["job"]
    paused = api_client.post(
        f"/nassav/api/tasks/jobs/{job.id}/pause",
        {"expected_version": job.version, "request_id": str(uuid4())},
        format="json",
    )
    assert paused.status_code == 202
    assert paused.json()["data"]["state"] == "paused"
    status = api_client.get(
        data["status_url"], HTTP_X_RESOURCE_JOB_TOKEN=data["status_token"]
    )
    assert status.status_code == 200
    assert status.json()["data"]["state"] == "paused"


@pytest.mark.django_db
def test_repeat_add_after_saved_resource_still_returns_owned_active_job(
    api_client, monkeypatch
):
    monkeypatch.setattr(scrape_jobs.run_resource_job, "apply_async", Mock())
    first = api_client.post(
        "/nassav/api/resource/jobs",
        {"action": "add", "avid": "PERSIST-2"},
        format="json",
    ).json()["data"]
    AVResource.objects.create(avid="PERSIST-2")
    repeated = api_client.post(
        "/nassav/api/resource/jobs",
        {"action": "add", "avid": "PERSIST-2"},
        format="json",
    )
    assert repeated.status_code == 202
    assert repeated.json()["data"]["duplicate"]
    assert repeated.json()["data"]["job_id"] == first["job_id"]
    assert TaskJob.objects.count() == TaskAttempt.objects.count() == 1


@pytest.mark.django_db
def test_other_operator_cannot_dedupe_or_control_active_scrape(
    api_client, operator_user, django_user_model, monkeypatch
):
    monkeypatch.setattr(scrape_jobs.run_resource_job, "apply_async", Mock())
    first = api_client.post(
        "/nassav/api/resource/jobs",
        {"action": "add", "avid": "PERSIST-3"},
        format="json",
    ).json()["data"]
    other = django_user_model.objects.create_user(username="other-scrape-owner")
    api_client.force_authenticate(other)
    assert (
        api_client.post(
            "/nassav/api/resource/jobs",
            {"action": "add", "avid": "PERSIST-3"},
            format="json",
        ).status_code
        == 403
    )
    assert (
        api_client.get(f"/nassav/api/tasks/jobs/{first['job_id']}").status_code == 403
    )
