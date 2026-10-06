"""Owner fencing uses real ephemeral Redis; cancellation uses a silent local CLI."""

import json
import subprocess
import sys
import time
from threading import Event, Timer
from unittest.mock import Mock

import pytest
from nassav.download_contracts import DownloadLeaseLost
from nassav.download_leases import DownloadLease, download_ownership
from test_session_lifecycle_contracts import isolated_redis as isolated_redis


def lease(client, avid="OWN-001"):
    return DownloadLease(avid, lambda: client, heartbeat_seconds=60)


def test_old_execution_cannot_release_renew_or_overwrite_successor(isolated_redis):
    client = isolated_redis
    old, successor = lease(client), lease(client)
    old.start()
    assert old.acquire_global()
    client.delete(old.task_key, old.GLOBAL_KEY)
    successor.start()
    assert successor.acquire_global()
    client.hset("nassav:task_queue", successor.avid, json.dumps({"state": "STARTED"}))
    assert successor.mutate("progress", "new-progress")
    assert not old.renew()
    with pytest.raises(DownloadLeaseLost):
        old.check()
    assert not old.release_global()
    for operation in (
        "progress",
        "state",
        "remove_progress",
        "remove_queue",
        "cleanup",
    ):
        assert not old.mutate(operation, "old-data")
    old.close()
    assert client.get(successor.task_key) == successor.owner.encode()
    assert client.get(successor.GLOBAL_KEY) == successor.owner.encode()
    assert client.get("nassav:task_progress:OWN-001") == b"new-progress"
    assert (
        json.loads(client.hget("nassav:task_queue", successor.avid))["state"]
        == "STARTED"
    )
    successor.close()
    assert not client.exists(successor.task_key, successor.GLOBAL_KEY)


def test_duplicate_delivery_has_distinct_owner_and_preserves_running_task(
    isolated_redis,
):
    client = isolated_redis
    running, duplicate = lease(client), lease(client)
    with download_ownership(running):
        running.start(30)
        assert client.ttl(running.task_key) <= 30
        with pytest.raises(DownloadLeaseLost), download_ownership(duplicate):
            duplicate.start()
        assert running.owner != duplicate.owner
        running.check()
        assert running.renew()


def test_heartbeat_signals_loss_without_progress_output(isolated_redis):
    client = isolated_redis
    owner = DownloadLease("OWN-002", lambda: client, heartbeat_seconds=0.02)
    with download_ownership(owner):
        owner.start()
        assert owner.acquire_global()
        client.set(owner.GLOBAL_KEY, "successor", ex=60)
        assert not owner.mutate("progress", "stale")
        assert not owner.mutate("state", "SUCCESS")
        deadline = time.monotonic() + 2
        while not owner.cancelled() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert owner.cancelled()
    assert client.get(owner.GLOBAL_KEY) == b"successor"


def test_task_losing_global_lease_cannot_report_or_persist_success(
    isolated_redis, monkeypatch
):
    from nassav import download_queue, tasks
    from nassav.download_persistence import download_persistence
    from nassav.services import video_download_service

    client = isolated_redis
    events = []
    completed, failed = Mock(), Mock()
    monkeypatch.setattr(download_queue, "get_redis_client", lambda: client)
    monkeypatch.setattr(download_queue, "get_full_task_queue", list)
    monkeypatch.setattr(
        download_queue, "notify_task_update", lambda name, data: events.append(name)
    )
    monkeypatch.setattr(download_persistence, "mark_completed", completed)
    monkeypatch.setattr(download_persistence, "mark_failed", failed)

    def download(avid, progress_callback, cancelled=None):
        client.set(DownloadLease.GLOBAL_KEY, "new-global-owner", ex=60)
        return True

    monkeypatch.setattr(video_download_service, "download_video", download)
    result = tasks.download_video_task.apply(
        args=("OWN-003",), task_id="redelivery"
    ).get()
    assert result["status"] == "failed"
    assert "task_completed" not in events
    assert events.count("task_failed") == 1
    completed.assert_not_called()
    failed.assert_not_called()
    assert client.get(DownloadLease.GLOBAL_KEY) == b"new-global-owner"


def test_silent_cli_is_terminated_when_lease_is_lost(monkeypatch, tmp_path):
    from nassav.m3u8downloader.N_m3u8DL_RE import N_m3u8DL_RE

    original_popen = subprocess.Popen
    processes = []

    def local_popen(command, **kwargs):
        process = original_popen(
            [sys.executable, "-u", "-c", "import time; time.sleep(60)"], **kwargs
        )
        processes.append(process)
        return process

    monkeypatch.setattr(subprocess, "Popen", local_popen)
    lost = Event()
    timer = Timer(0.15, lost.set)
    timer.start()
    started = time.monotonic()
    try:
        assert not N_m3u8DL_RE().download(
            "https://offline.invalid/video.m3u8",
            tmp_path,
            "OWN-004",
            referer="https://offline.invalid/",
            user_agent="test",
            cancelled=lost.is_set,
        )
    finally:
        timer.cancel()
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.wait()
    assert time.monotonic() - started < 4
    assert processes and processes[0].poll() is not None


def test_renewal_failure_cancels_and_failed_release_does_not_skip_cleanup(
    isolated_redis,
):
    import redis

    client = isolated_redis
    owner = lease(client, "OWN-005")
    owner.start()
    assert owner.acquire_global()
    unavailable = Mock()
    unavailable.eval.side_effect = redis.ConnectionError("isolated failure")
    owner.client_factory = lambda: unavailable
    assert not owner.renew()
    assert owner.cancelled()
    assert client.get(owner.task_key) == owner.owner.encode()

    class ReleaseFailure:
        def eval(self, script, count, *args):
            if args[0] == owner.GLOBAL_KEY:
                raise redis.ConnectionError("release failed")
            return client.eval(script, count, *args)

    owner.client_factory = lambda: ReleaseFailure()
    owner.close()
    assert not client.exists(owner.task_key)
    assert client.get(owner.GLOBAL_KEY) == owner.owner.encode()
