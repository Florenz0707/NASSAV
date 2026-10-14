"""Recovery must prove exit before releasing owners or touching private files."""

import json
import os
import subprocess
import sys
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from django.utils import timezone

from nassav.task_assets import TaskAssets
from nassav.task_control_rules import TaskExecutionInvalid
from nassav.task_models import TaskAttempt
from nassav.task_processes import process_identity, identity_status
from nassav.task_records import DjangoTaskRecords
from nassav.task_recovery import TaskRecovery
from test_session_lifecycle_contracts import isolated_redis as isolated_redis


@pytest.fixture
def context(db, operator_user, tmp_path, isolated_redis):
    records = DjangoTaskRecords()
    assets = TaskAssets(
        {kind: tmp_path / kind for kind in ("cover", "avatar", "video")}, records
    )
    job, _ = records.create(
        "download", "RECOVER-1", owner_id=operator_user.pk, action="download"
    )
    token = records.claim(job["job_id"], job["task_id"], kind="download", role="main")
    private = assets.workspace(token, "video")
    (private / "partial.ts").write_bytes(b"private video")
    events = SimpleNamespace(flush=lambda _: None)
    recovery = TaskRecovery(
        records,
        assets,
        dispatch=lambda _: {},
        events=events,
        redis_client=lambda: isolated_redis,
    )
    return records, assets, job, token, recovery, isolated_redis


def set_identity(context, worker, extra=None):
    records, _, _, token, _, _ = context
    identity = {
        **{f"worker_{key}": value for key, value in worker.items()},
        **(extra or {}),
    }
    records.execution_identity(token, identity)
    TaskAttempt.objects.filter(pk=token.attempt_id).update(
        heartbeat_at=timezone.now() - timedelta(seconds=60)
    )
    return identity


def dead_identity():
    process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        return process_identity(process.pid)
    finally:
        process.terminate()
        process.wait(timeout=3)


def request(context, action):
    records, _, job, _, _, _ = context
    latest = records.get(job["job_id"])
    return records.request(
        job["job_id"],
        action,
        expected_version=latest["version"],
        request_id=str(uuid4()),
        actor_id=None,
        allow_all=True,
    )


def test_stale_heartbeat_is_not_exit_proof(context):
    records, assets, job, _, recovery, _ = context
    set_identity(context, process_identity(os.getpid()))
    request(context, "cancel")
    result = recovery.scan(stale_seconds=1)
    assert result["alive"] == 1
    assert records.get(job["job_id"])["state"] == "cancelling"
    assert (assets.roots["video"] / ".tasks" / job["job_id"]).exists()


def test_foreign_or_partial_identity_keeps_writer_and_files(context):
    records, assets, job, _, recovery, _ = context
    identity = process_identity(os.getpid())
    identity["host"] = "unverifiable-other-instance"
    set_identity(context, identity)
    request(context, "cancel")
    result = recovery.scan(stale_seconds=1)
    snapshot = records.get(job["job_id"])
    assert result["unconfirmed"] == 1
    assert snapshot["state"] == "cancelling"
    assert snapshot["error_code"] == "RECOVERY_UNCONFIRMED"
    assert (assets.roots["video"] / ".tasks" / job["job_id"]).exists()
    assert identity_status({"pid": os.getpid()}) == "unknown"


def test_dead_worker_orphan_is_stopped_before_cancel_cleanup(context):
    records, assets, job, token, recovery, _ = context
    scope = {
        "job_id": token.job_id,
        "attempt_id": token.attempt_id,
        "owner": token.owner,
    }
    worker = dead_identity()
    child = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        env={**os.environ, "NASSAV_TASK_WRITER": json.dumps(scope)},
        start_new_session=True,
    )
    try:
        # Deliberately no DB child PID: crash can happen between spawn and registration.
        assert identity_status(worker) == "dead", (
            worker,
            process_identity(os.getpid()),
        )
        set_identity(context, worker)
        original = assets.roots["video"] / "RECOVER-1.mp4"
        original.write_bytes(b"existing formal video")
        request(context, "cancel")
        result = recovery.scan(stale_seconds=1)
        assert result["recovered"] == 1, (result, records.get(job["job_id"])["message"])
        child.wait(timeout=3)
        assert result["recovered"] == result["cleaned"] == 1
        assert records.get(job["job_id"])["state"] == "cancelled"
        assert original.read_bytes() == b"existing formal video"
        assert not (assets.roots["video"] / ".tasks" / job["job_id"]).exists()
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=3)


def test_abandoned_download_pauses_and_releases_only_owned_keys(context):
    records, assets, job, _, recovery, client = context
    worker = dead_identity()
    assert identity_status(worker) == "dead", (worker, process_identity(os.getpid()))
    identity = set_identity(context, worker, {"lease_owner": "old-owner"})
    client.set("nassav:task_lock:RECOVER-1", "old-owner")
    client.set("nassav:global_download_lock", "successor-owner")
    client.set("nassav:task_progress:RECOVER-1", "private progress")
    client.hset("nassav:task_queue", "RECOVER-1", "old queue")
    result = recovery.scan(stale_seconds=1)
    assert result["recovered"] == 1, (result, records.get(job["job_id"])["message"])
    snapshot = records.get(job["job_id"])
    assert snapshot["state"] == "paused"
    assert client.get("nassav:global_download_lock") == b"successor-owner"
    assert client.get("nassav:task_lock:RECOVER-1") is None
    assert client.get("nassav:task_progress:RECOVER-1") is None
    assert (assets.roots["video"] / ".tasks" / job["job_id"]).exists()
    assert identity["lease_owner"] == "old-owner"
    resumed = request(context, "resume")
    assert resumed["job_id"] == job["job_id"] and resumed["task_id"] != job["task_id"]


def test_recovery_rechecks_heartbeat_inside_write_fence(context):
    records, _, job, token, _, _ = context
    identity = set_identity(context, dead_identity())
    cutoff = timezone.now() - timedelta(seconds=1)
    records.heartbeat(token)
    with pytest.raises(TaskExecutionInvalid):
        records.recover_execution(token, identity=identity, stale_before=cutoff)
    assert records.get(job["job_id"])["state"] == "running"


def test_sent_without_claim_requeues_same_attempt_but_not_running(context):
    records, _, _, token, _, _ = context
    second, _ = records.create("scrape", "RECOVER-2", owner_id=None, action="add")
    records.dispatch_pending(lambda _: None)
    TaskAttempt.objects.filter(pk=second["task_id"]).update(
        dispatched_at=timezone.now() - timedelta(minutes=10)
    )
    assert (
        records.retry_unclaimed(sent_before=timezone.now() - timedelta(minutes=5)) == 1
    )
    sent = []
    records.dispatch_pending(sent.append)
    assert [ticket["task_id"] for ticket in sent] == [second["task_id"]]
    assert TaskAttempt.objects.get(pk=token.attempt_id).state == "running"


def test_explicit_confirmation_requires_assertion_and_rejects_alive_worker(context):
    records, _, job, token, recovery, _ = context
    set_identity(context, process_identity(os.getpid()))
    with pytest.raises(ValueError):
        recovery.confirm_stopped(token.attempt_id, all_writers_stopped=False)
    with pytest.raises(TaskExecutionInvalid):
        recovery.confirm_stopped(token.attempt_id, all_writers_stopped=True)
    assert records.get(job["job_id"])["state"] == "running"


def test_confirmed_foreign_instance_recovery_is_idempotent_and_keeps_private_files(
    context,
):
    records, assets, job, token, recovery, _ = context
    identity = process_identity(os.getpid())
    identity["host"] = "old-confirmed-container"
    set_identity(context, identity)
    snapshot = recovery.confirm_stopped(token.attempt_id, all_writers_stopped=True)
    assert snapshot["state"] == "paused"
    assert (
        snapshot["version"]
        == recovery.confirm_stopped(token.attempt_id, all_writers_stopped=True)[
            "version"
        ]
    )
    assert (assets.roots["video"] / ".tasks" / job["job_id"]).exists()


def test_recent_heartbeat_cannot_be_overridden_by_manual_confirmation(context):
    records, _, _, token, recovery, _ = context
    identity = process_identity(os.getpid())
    identity["host"] = "old-container"
    set_identity(context, identity)
    records.heartbeat(token)
    with pytest.raises(TaskExecutionInvalid):
        recovery.confirm_stopped(token.attempt_id, all_writers_stopped=True)


def test_stopped_publication_is_retried_and_resume_remains_blocked_until_recovered(
    context, monkeypatch
):
    from nassav.task_models import TaskArtifact
    from nassav.task_control_rules import TaskConflict

    records, assets, job, token, recovery, _ = context
    worker = dead_identity()
    set_identity(context, worker)
    records.recover_execution(
        token,
        identity=TaskAttempt.objects.get(pk=token.attempt_id).execution_identity,
        stale_before=timezone.now() - timedelta(seconds=1),
    )
    TaskArtifact.objects.create(
        job_id=job["job_id"],
        root="cover",
        relative_path="cover.jpg",
        state="promoting",
        target_path="RECOVER-1.jpg",
    )
    called = []

    def fail(_):
        called.append("failed")
        raise OSError("temporary permissions")

    monkeypatch.setattr(assets, "recover", fail)
    recovery.scan(stale_seconds=1)
    assert records.get(job["job_id"])["error_code"] == "ASSET_RECOVERY_PENDING"
    assert "resume" not in records.get(job["job_id"])["allowed_actions"]
    with pytest.raises(TaskConflict):
        request(context, "resume")

    def complete(_):
        called.append("completed")
        TaskArtifact.objects.filter(job_id=job["job_id"], state="promoting").update(
            state="staged"
        )

    monkeypatch.setattr(assets, "recover", complete)
    recovery.scan(stale_seconds=1)
    assert called == ["failed", "completed"]
    assert "resume" in records.get(job["job_id"])["allowed_actions"]
    assert request(context, "resume")["state"] == "queued"


def test_management_confirmation_requires_both_arguments(context):
    from django.core.management import call_command
    from django.core.management.base import CommandError

    _, _, _, token, _, _ = context
    with pytest.raises(CommandError):
        call_command("recover_tasks", confirm_stopped_attempt=token.attempt_id)
    with pytest.raises(CommandError):
        call_command("recover_tasks", all_writers_stopped=True)


def test_management_command_emits_only_public_recovery_summary(context, monkeypatch):
    import io
    from django.core.management import call_command
    from nassav import composition

    _, _, _, _, recovery, _ = context
    monkeypatch.setattr(composition, "build_task_recovery", lambda: recovery)
    output = io.StringIO()
    call_command("recover_tasks", stdout=output)
    result = json.loads(output.getvalue())
    assert result["recovered"] == result["failed"] == 0
    assert "checkpoint" not in result


def test_recovery_reconciles_user_operations_with_a_bounded_batch(context):
    from unittest.mock import Mock

    recovery = context[4]
    recovery.reconcile = Mock(return_value={"projected": 1, "skipped": 0})
    result = recovery.scan(limit=300)
    recovery.reconcile.assert_called_once_with(limit=200)
    assert result["operations"] == {"projected": 1, "skipped": 0}


def test_projection_failure_does_not_skip_task_recovery(context):
    from unittest.mock import Mock

    recovery = context[4]
    recovery.reconcile = Mock(
        side_effect=RuntimeError("database temporarily unavailable")
    )
    result = recovery.scan()
    assert result["failed"] == 1
    assert result["dispatch"] == {}
