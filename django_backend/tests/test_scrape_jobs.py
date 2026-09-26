"""Offline coverage for scrape submission, snapshots, and API behavior."""

from unittest.mock import Mock

import pytest
from nassav import scrape_jobs


class MemoryJobStore(scrape_jobs.JobStore):
    def __init__(self):
        self.owners = {}
        self.snapshots = {}

    def acquire(self, avid, task_id):
        owner = self.owners.get(avid)
        if owner is None:
            self.owners[avid] = task_id
            return None
        return owner

    def release(self, avid, task_id):
        if self.owners.get(avid) == task_id:
            del self.owners[avid]

    def renew(self, avid, task_id):
        return self.owners.get(avid) == task_id

    def get(self, task_id):
        return self.snapshots.get(task_id)

    def save(self, snapshot):
        existing = self.get(snapshot["task_id"])
        if existing and existing["state"] in scrape_jobs.TERMINAL_STATES:
            return existing
        result = {
            **snapshot,
            "version": (existing or {}).get("version", 0) + 1,
            "updated_at": 123.0,
        }
        self.snapshots[snapshot["task_id"]] = result
        return result

    def delete(self, task_id):
        self.snapshots.pop(task_id, None)


@pytest.mark.django_db
def test_submission_deduplicates_add(monkeypatch):
    store = MemoryJobStore()
    enqueue = Mock()
    monkeypatch.setattr(scrape_jobs.run_resource_job, "apply_async", enqueue)
    monkeypatch.setattr(scrape_jobs, "_publish", Mock())
    first, duplicate = scrape_jobs.submit_resource_job("add", " abc-1 ", store=store)
    second, duplicate_again = scrape_jobs.submit_resource_job(
        "add", "ABC-1", store=store
    )
    assert duplicate is False and duplicate_again is True
    assert first == second and first["avid"] == "ABC-1"
    assert enqueue.call_count == 1
    assert enqueue.call_args.kwargs["queue"] == "scrape"
    assert enqueue.call_args.kwargs["expires"] == scrape_jobs.LOCK_TTL


@pytest.mark.django_db
def test_submission_failure_releases_owner_and_snapshot(monkeypatch):
    store = MemoryJobStore()
    monkeypatch.setattr(
        scrape_jobs.run_resource_job,
        "apply_async",
        Mock(side_effect=RuntimeError("broker down")),
    )
    with pytest.raises(RuntimeError, match="broker down"):
        scrape_jobs.submit_resource_job("add", "ABC-2", store=store)
    assert store.owners == {} and store.snapshots == {}


@pytest.mark.django_db
def test_worker_reports_real_stages_and_terminal_result(monkeypatch):
    store = MemoryJobStore()
    task_id = "job-1"
    store.acquire("ABC-3", task_id)
    store.save(
        {
            "task_id": task_id,
            "job_type": "scrape",
            "action": "add",
            "avid": "ABC-3",
            "state": "queued",
            "stage": None,
        }
    )
    monkeypatch.setattr(scrape_jobs, "RedisJobStore", lambda: store)
    publish = Mock()
    monkeypatch.setattr(scrape_jobs, "_publish", publish)
    monkeypatch.setattr(
        scrape_jobs.AVResource.objects,
        "filter",
        lambda **kwargs: Mock(exists=lambda: False),
    )

    def add_resource(avid, source, progress):
        for stage in (
            "source_lookup",
            "metadata",
            "cover",
            "saving",
            "translation_queued",
        ):
            progress(stage)
        return {"resource": {"avid": avid}}

    monkeypatch.setattr(
        "nassav.resource_service.resource_service.add_resource", add_resource
    )
    result = scrape_jobs.run_resource_job.apply(
        args=["add", "ABC-3", "any", {}], task_id=task_id
    ).get()
    assert result == {"resource_avid": "ABC-3"}
    assert store.get(task_id)["state"] == "succeeded" and store.owners == {}
    assert [call.args[0]["stage"] for call in publish.call_args_list] == [
        None,
        "source_lookup",
        "metadata",
        "cover",
        "saving",
        "translation_queued",
        None,
    ]


@pytest.mark.django_db
def test_api_batch_keeps_partial_results(api_client, monkeypatch):
    def submit(action, avid, source, options):
        if avid == "BAD-1":
            raise RuntimeError("broker down")
        return {"task_id": "00000000-0000-0000-0000-000000000001"}, False

    monkeypatch.setattr(scrape_jobs, "submit_resource_job", submit)
    response = api_client.post(
        "/nassav/api/resource/jobs/batch",
        {
            "actions": [
                {"action": "add", "avid": "GOOD-1"},
                {"action": "add", "avid": "BAD-1"},
            ]
        },
        format="json",
    )
    assert response.status_code == 202
    assert [item["code"] for item in response.json()["data"]["results"]] == [202, 503]
    assert api_client.get("/nassav/api/resource/jobs/not-a-uuid").status_code == 404


@pytest.mark.django_db
def test_status_endpoint_returns_snapshot(api_client, monkeypatch):
    monkeypatch.setattr(
        scrape_jobs,
        "get_resource_job",
        lambda task_id: {
            "task_id": task_id,
            "state": "running",
            "stage": "source_lookup",
        },
    )
    task_id = "00000000-0000-0000-0000-000000000001"
    path = f"/nassav/api/resource/jobs/{task_id}"
    assert api_client.get(path).status_code == 403
    response = api_client.get(
        path, HTTP_X_RESOURCE_JOB_TOKEN=scrape_jobs.job_token(task_id)
    )
    assert response.status_code == 200
    assert response.json()["data"]["stage"] == "source_lookup"


@pytest.mark.django_db
def test_inflight_duplicate_wins_over_newly_saved_database_row(resource_factory):
    store = MemoryJobStore()
    store.acquire("ABC-4", "existing-job")
    store.save(
        {
            "task_id": "existing-job",
            "avid": "ABC-4",
            "state": "running",
            "stage": "saving",
        }
    )
    resource_factory(avid="ABC-4")
    snapshot, duplicate = scrape_jobs.submit_resource_job("add", "abc-4", store=store)
    assert duplicate is True and snapshot["task_id"] == "existing-job"


@pytest.mark.django_db
def test_existing_resource_does_not_leave_lock(resource_factory):
    from nassav.resource_service import ResourceAlreadyExistsError

    store = MemoryJobStore()
    resource_factory(avid="ABC-5")
    with pytest.raises(ResourceAlreadyExistsError):
        scrape_jobs.submit_resource_job("add", "ABC-5", store=store)
    assert store.owners == {}


def test_lost_worker_snapshot_becomes_failed(monkeypatch):
    store = MemoryJobStore()
    store.save(
        {
            "task_id": "lost-job",
            "avid": "ABC-6",
            "state": "running",
            "stage": "source_lookup",
        }
    )
    monkeypatch.setattr(scrape_jobs, "_publish", Mock())
    snapshot = scrape_jobs.get_resource_job("lost-job", store=store)
    assert snapshot["state"] == "failed"
    assert snapshot["error_code"] == "WORKER_LOST"
    assert store.owners == {}


@pytest.mark.django_db
def test_batch_invalid_item_does_not_block_valid_item(api_client, monkeypatch):
    monkeypatch.setattr(
        scrape_jobs, "submit_resource_job", lambda *args: ({"task_id": "job-1"}, False)
    )
    response = api_client.post(
        "/nassav/api/resource/jobs/batch",
        {
            "actions": [
                {"action": "remove", "avid": "ABC-1"},
                {"action": "add", "avid": "ABC-2"},
            ]
        },
        format="json",
    )
    assert response.status_code == 202
    assert [item["code"] for item in response.json()["data"]["results"]] == [400, 202]


@pytest.mark.django_db
def test_single_api_returns_202_with_status_capability(api_client, monkeypatch):
    task_id = "00000000-0000-0000-0000-000000000002"
    monkeypatch.setattr(
        scrape_jobs,
        "submit_resource_job",
        lambda *args: ({"task_id": task_id, "state": "queued", "avid": "ABC-7"}, False),
    )
    response = api_client.post(
        "/nassav/api/resource/jobs", {"action": "add", "avid": "abc-7"}, format="json"
    )
    assert response.status_code == 202
    data = response.json()["data"]
    assert data["task_id"] == task_id
    assert data["job"]["state"] == "queued"
    assert scrape_jobs.valid_job_token(task_id, data["status_token"])
