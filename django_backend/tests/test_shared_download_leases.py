"""Shared work IDs isolate task/projection keys while retaining global capacity."""

from uuid import uuid4

import pytest

from nassav.download_leases import DownloadLease
from nassav.task_recovery import release_owned_download
from nassav.task_control_rules import TaskExecutionInvalid
from test_session_lifecycle_contracts import isolated_redis as isolated_redis


def test_same_avid_shared_leases_do_not_delete_each_other_or_legacy_state(
    isolated_redis,
):
    ids = [str(uuid4()), str(uuid4())]
    first, second = [
        DownloadLease("LEASE-001", lambda: isolated_redis, job_id=identity)
        for identity in ids
    ]
    legacy = DownloadLease("LEASE-001", lambda: isolated_redis)
    try:
        for lease in (first, second, legacy):
            lease.start()
        assert first.acquire_global()
        assert not second.acquire_global() and not legacy.acquire_global()
        isolated_redis.set(legacy.progress_key, "legacy progress")
        isolated_redis.hset(legacy.queue_key, legacy.avid, "legacy queue")
        isolated_redis.set(second.progress_key, "second progress")
        isolated_redis.hset(second.queue_key, second.job_id, "second queue")
        first.close()
        assert isolated_redis.get(legacy.progress_key) == b"legacy progress"
        assert isolated_redis.hget(legacy.queue_key, legacy.avid) == b"legacy queue"
        assert isolated_redis.get(second.progress_key) == b"second progress"
        assert isolated_redis.hget(second.queue_key, second.job_id) == b"second queue"
        assert second.acquire_global()
    finally:
        for lease in (first, second, legacy):
            lease.close()


def test_recovery_derives_shared_keys_from_trusted_job_and_checks_owner(isolated_redis):
    identity = str(uuid4())
    lease = DownloadLease("LEASE-002", lambda: isolated_redis, job_id=identity)
    try:
        lease.start()
        assert lease.acquire_global()
        data = lease.recovery_identity()
        data["lease_task_key"] = "arbitrary-untrusted-key"
        isolated_redis.set("arbitrary-untrusted-key", "preserve")
        with pytest.raises(TaskExecutionInvalid):
            release_owned_download(
                data, lease.avid, isolated_redis, job_id=str(uuid4())
            )
        assert isolated_redis.get(lease.task_key) == lease.owner.encode()
        release_owned_download(data, lease.avid, isolated_redis, job_id=identity)
        assert isolated_redis.get(lease.task_key) is None
        assert isolated_redis.get(lease.GLOBAL_KEY) is None
        assert isolated_redis.get("arbitrary-untrusted-key") == b"preserve"
    finally:
        lease.close()
