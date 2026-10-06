"""Consumers exercise the durable controls, including races and delayed delivery."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.db import close_old_connections
from django.utils import timezone
from datetime import timedelta

from nassav.task_control_rules import (
    TaskCancelRequested,
    TaskConflict,
    TaskExecutionInvalid,
    TaskForbidden,
    TaskPauseRequested,
)
from nassav.task_models import TaskArtifact, TaskAttempt, TaskJob
from nassav.task_records import DjangoTaskRecords


@pytest.fixture
def owner(db):
    return get_user_model().objects.create_user(username="task-owner")


@pytest.fixture
def records():
    return DjangoTaskRecords()


def create(records, owner, avid="TASK-1", kind="download", action="download"):
    snapshot, duplicate = records.create(kind, avid, owner_id=owner.pk, action=action)
    assert not duplicate
    return snapshot


def request(records, owner, job, action, request_id=None):
    return records.request(
        job["job_id"],
        action,
        expected_version=job["version"],
        request_id=request_id or str(uuid4()),
        actor_id=owner.pk,
    )


def test_pause_queue_resume_uses_new_attempt_and_rejects_old_delivery(records, owner):
    job = create(records, owner)
    paused = request(records, owner, job, "pause")
    assert paused["state"] == "paused"
    assert records.create("download", "task-1", owner_id=owner.pk, action="download")[1]
    assert (
        records.dispatch_pending(
            lambda ticket: pytest.fail("paused task was dispatched")
        )["sent"]
        == 0
    )
    resumed = request(records, owner, paused, "resume")
    assert resumed["job_id"] == job["job_id"]
    assert resumed["generation"] == 2
    assert resumed["task_id"] != job["task_id"]
    with pytest.raises(TaskExecutionInvalid):
        records.claim(job["job_id"], job["task_id"])
    token = records.claim(resumed["job_id"], resumed["task_id"])
    assert records.check(token) is None


def test_paused_job_survives_old_redis_ttl_and_new_adapter_instance(records, owner):
    job = create(records, owner)
    paused = request(records, owner, job, "pause")
    TaskJob.objects.filter(pk=job["job_id"]).update(
        updated_at=timezone.now() - timedelta(days=3)
    )
    restored = DjangoTaskRecords().get(job["job_id"])
    assert restored["state"] == "paused"
    assert restored["version"] == paused["version"]
    assert restored["finished_at"] is None
    assert DjangoTaskRecords().create(
        "download", "TASK-1", owner_id=owner.pk, action="download"
    )[1]


def test_pause_running_waits_for_exit_and_preserves_checkpoint(records, owner):
    job = create(records, owner)
    token = records.claim(job["job_id"], job["task_id"])
    current = records.checkpoint(token, "video_download", {"segments": [1, 2]})
    pausing = request(records, owner, current, "pause")
    assert pausing["state"] == "pausing"
    with pytest.raises(TaskPauseRequested):
        records.finish(token, "succeeded")
    with pytest.raises(TaskConflict):
        request(records, owner, pausing, "resume")
    paused = records.acknowledge_stop(token, checkpoint={"segments": [1, 2, 3]})
    assert paused["checkpoint"]["segments"] == [1, 2, 3]
    assert paused["state"] == "paused"
    assert records.create("download", "task-1", owner_id=owner.pk, action="download")[1]


def test_cancel_dominates_pause_and_cleanup_retains_history(records, owner):
    job = create(records, owner, kind="scrape", action="add")
    token = records.claim(job["job_id"], job["task_id"])
    pausing = request(records, owner, records.get(job["job_id"]), "pause")
    cancelling = request(records, owner, pausing, "cancel")
    assert cancelling["state"] == "cancelling"
    TaskArtifact.objects.create(
        job_id=job["job_id"], root="cover", relative_path="cover.jpg", kind="cover"
    )
    with pytest.raises(TaskCancelRequested):
        records.checkpoint(token, "saving")
    cancelled = records.acknowledge_stop(token)
    assert cancelled["state"] == "cancelled"
    assert cancelled["cleanup_state"] == "pending"
    assert TaskJob.objects.get(pk=job["job_id"]).active_key is None
    assert [event["state"] for event in cancelled["timeline"]] == [
        "queued",
        "running",
        "pausing",
        "cancelling",
        "cancelled",
    ]
    with pytest.raises(TaskExecutionInvalid):
        records.finish(token, "succeeded")


def test_cancel_queued_is_confirmed_without_writer(records, owner):
    job = create(records, owner)
    cancelled = request(records, owner, job, "cancel")
    assert cancelled["state"] == "cancelled"
    assert cancelled["cleanup_state"] == "not_required"
    with pytest.raises(TaskExecutionInvalid):
        records.claim(job["job_id"], job["task_id"])
    assert create(records, owner)["job_id"] != job["job_id"]


def test_old_execution_cannot_write_after_resume(records, owner):
    job = create(records, owner)
    old = records.claim(job["job_id"], job["task_id"])
    request(records, owner, records.get(job["job_id"]), "pause")
    paused = records.acknowledge_stop(old)
    resumed = request(records, owner, paused, "resume")
    new = records.claim(resumed["job_id"], resumed["task_id"])
    records.checkpoint(new, "merging", {"fresh": True})
    with pytest.raises(TaskExecutionInvalid):
        records.checkpoint(old, "saving", {"fresh": False})
    with pytest.raises(TaskExecutionInvalid):
        records.finish(old, "failed")
    assert not records.heartbeat(old)
    assert records.get(job["job_id"])["checkpoint"]["fresh"] is True


def test_duplicate_command_does_not_repeat_resume_even_after_later_change(
    records, owner
):
    job = create(records, owner)
    paused = request(records, owner, job, "pause")
    command_id = str(uuid4())
    resumed = request(records, owner, paused, "resume", command_id)
    assert request(records, owner, paused, "resume", command_id) == resumed
    later = request(records, owner, resumed, "pause")
    assert request(records, owner, paused, "resume", command_id)["state"] == "paused"
    assert TaskAttempt.objects.filter(job_id=job["job_id"]).count() == 2
    with pytest.raises(TaskConflict):
        request(records, owner, later, "cancel", command_id)


def test_version_and_permissions_protect_controls(records, owner):
    job = create(records, owner)
    records.claim(job["job_id"], job["task_id"])
    with pytest.raises(TaskConflict) as error:
        request(records, owner, job, "cancel")
    assert error.value.snapshot["state"] == "running"
    with pytest.raises(TaskForbidden):
        records.request(
            job["job_id"],
            "cancel",
            expected_version=2,
            request_id=str(uuid4()),
            actor_id=owner.pk + 100,
        )
    assert records.get(job["job_id"])["state"] == "running"


@pytest.mark.parametrize("state", ["succeeded", "failed"])
def test_terminal_result_cannot_be_resumed_or_cancelled(records, owner, state):
    job = create(records, owner)
    token = records.claim(job["job_id"], job["task_id"])
    terminal = records.finish(token, state)
    for action in ("pause", "resume", "cancel"):
        with pytest.raises(TaskConflict):
            request(records, owner, terminal, action)
    assert records.get(job["job_id"])["state"] == state
    assert create(records, owner)["job_id"] != job["job_id"]


def test_broker_failure_retains_dispatch_record_and_recovery_uses_same_id(
    records, owner
):
    job = create(records, owner)

    def unavailable(ticket):
        raise OSError("broker unavailable")

    assert records.dispatch_pending(unavailable) == {"sent": 0, "failed": 1}
    tickets = []
    assert records.dispatch_pending(tickets.append) == {"sent": 1, "failed": 0}
    assert tickets[0]["task_id"] == job["task_id"]
    assert records.get(job["job_id"])["state"] == "queued"
    records.claim(job["job_id"], job["task_id"])
    with pytest.raises(TaskExecutionInvalid):
        records.claim(job["job_id"], job["task_id"])


def test_worker_can_start_before_publish_ack_without_state_regression(records, owner):
    job = create(records, owner)

    def immediate(ticket):
        records.claim(ticket["job_id"], ticket["task_id"])

    records.dispatch_pending(immediate)
    assert records.get(job["job_id"])["state"] == "running"
    assert TaskAttempt.objects.get(pk=job["task_id"]).state == "running"


def test_pause_during_dispatch_invalidates_delivered_ticket(records, owner):
    job = create(records, owner)

    def racing(ticket):
        request(records, owner, job, "pause")

    records.dispatch_pending(racing)
    assert TaskAttempt.objects.get(pk=job["task_id"]).state == "invalidated"
    with pytest.raises(TaskExecutionInvalid):
        records.claim(job["job_id"], job["task_id"])


@pytest.mark.django_db(transaction=True)
def test_concurrent_delivery_only_one_worker_claims(records, owner):
    job = create(records, owner)
    barrier = Barrier(2)

    def claim_once():
        close_old_connections()
        try:
            barrier.wait(timeout=5)
            return records.claim(job["job_id"], job["task_id"])
        except (TaskExecutionInvalid, TaskConflict):
            return None
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: claim_once(), range(2)))
    assert sum(result is not None for result in results) == 1
    assert records.get(job["job_id"])["state"] == "running"


@pytest.mark.django_db(transaction=True)
def test_concurrent_creation_reserves_one_active_job(records, owner):
    barrier = Barrier(2)

    def create_once():
        close_old_connections()
        try:
            barrier.wait(timeout=5)
            return records.create(
                "download", "TASK-1", owner_id=owner.pk, action="download"
            )
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: create_once(), range(2)))
    assert sorted(duplicate for _, duplicate in results) == [False, True]
    assert len({snapshot["job_id"] for snapshot, _ in results}) == 1


@pytest.mark.django_db(transaction=True)
def test_concurrent_control_commands_have_one_version_winner(records, owner):
    job = create(records, owner)
    barrier = Barrier(2)

    def control(action):
        close_old_connections()
        try:
            barrier.wait(timeout=5)
            return request(records, owner, job, action)
        except TaskConflict:
            return None
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(control, ["pause", "cancel"]))
    assert sum(result is not None for result in results) == 1
    current = records.get(job["job_id"])
    assert current["version"] == 2
    assert current["state"] in {"paused", "cancelled"}
