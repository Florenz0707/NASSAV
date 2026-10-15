"""Actual journaled images/MP4; GC touches only proven immutable version paths."""

from datetime import timedelta
from unittest.mock import Mock

import pytest
from django.utils import timezone

from nassav.resource_gc import ResourceReclaimer, GcDeferred
from nassav.resource_gc_storage import GcFileStorage
from nassav.resource_gc_models import ResourceGcJob, ResourceGcAsset
from nassav.resource_version_models import ResourceVersion
from nassav.library_models import ResourcePoolEntry, UserLibraryEntry
from nassav.personal_models import UserWatchHistory
from nassav.task_models import TaskAssetTarget
from test_resource_gc_ledger import unheld as unheld, release
from test_version_source_playback import source_versions as source_versions
from test_version_publication import environment as environment
from test_version_local_playback import clip as clip

pytestmark = pytest.mark.django_db


def engine(unheld, environment, **kwargs):
    _, records, version = unheld
    return ResourceReclaimer(
        records, GcFileStorage(environment[2]), **kwargs
    ), records.enqueue(version.pool_id, version.pk)["job_id"]


def path_for(roots, version):
    asset = version.manifest[0]
    return roots[asset["root"]] / asset["path"]


def test_private_version_cleanup_preserves_other_holder_and_stable_locks(
    unheld, environment
):
    (_, _, entries, _), records, version = unheld
    first = path_for(environment[2], version)
    second = path_for(environment[2], entries[1].current_version)
    before = second.read_bytes()
    runtime, job_id = engine(unheld, environment)
    assert runtime.run(job_id)["state"] == "completed"
    assert not first.exists() and second.read_bytes() == before
    version.refresh_from_db()
    assert version.state == "reclaimed" and version.metadata == {}
    assert UserLibraryEntry.objects.filter(pk=entries[1].pk).exists()
    marker = TaskAssetTarget.objects.get(
        root=version.manifest[0]["root"], relative_path=version.manifest[0]["path"]
    )
    assert marker.sha256 == ""
    assert ResourceGcAsset.objects.get(job_id=job_id).state == "deleted"
    assert list(
        (environment[2]["cover"].parent / ".nassav-delete-locks").glob("*.lock")
    )
    assert runtime.run(job_id)["state"] == "completed"


def test_permission_failure_keeps_tombstone_and_retry_is_owned(
    unheld, environment, monkeypatch
):
    runtime, job_id = engine(unheld, environment)
    storage = runtime.storage
    original = storage.deletion
    from contextlib import contextmanager

    @contextmanager
    def failing(asset, check):
        with original(asset, check) as (stamp, remove):
            yield stamp, Mock(side_effect=PermissionError("Denied"))

    monkeypatch.setattr(storage, "deletion", failing)
    assert runtime.run(job_id)["state"] == "cleanup_failed"
    version = unheld[2]
    version.refresh_from_db()
    assert (
        version.state == "cleanup_failed" and path_for(environment[2], version).exists()
    )
    assert ResourceGcAsset.objects.get(job_id=job_id).state == "verified"
    monkeypatch.setattr(storage, "deletion", original)
    assert runtime.run(job_id)["state"] == "completed"


def test_crash_after_unlink_before_db_commit_recovers_verified_missing_file(
    unheld, environment, monkeypatch
):
    runtime, job_id = engine(unheld, environment)
    original = runtime.records.unlink

    def interrupted(token, asset_id, remove):
        def crash():
            remove()
            raise RuntimeError("simulated process failure after unlink")

        return original(token, asset_id, crash)

    monkeypatch.setattr(runtime.records, "unlink", interrupted)
    assert runtime.run(job_id)["state"] == "cleanup_failed"
    assert not path_for(environment[2], unheld[2]).exists()
    assert ResourceGcAsset.objects.get(job_id=job_id).state == "verified"
    monkeypatch.setattr(runtime.records, "unlink", original)
    assert runtime.run(job_id)["state"] == "completed"


@pytest.mark.parametrize(
    "change", ["hash", "symlink", "directory_symlink", "missing", "unknown"]
)
def test_unknown_or_changed_files_are_never_wiped(unheld, environment, change):
    runtime, job_id = engine(unheld, environment)
    version = unheld[2]
    path = path_for(environment[2], version)
    outside = environment[2]["cover"].parent / "outside.jpg"
    outside.write_bytes(b"outside sentinel")
    if change == "hash":
        path.write_bytes(b"x" * path.stat().st_size)
    elif change == "symlink":
        path.unlink()
        path.symlink_to(outside)
    elif change == "directory_symlink":
        folder = outside.parent / "outside-dir"
        folder.mkdir()
        (folder / path.name).write_bytes(b"outside version sentinel")
        path.parent.rename(path.parent.with_name(path.parent.name + "-saved"))
        path.parent.symlink_to(folder, target_is_directory=True)
    elif change == "missing":
        path.unlink()
    else:
        (path.parent / "unregistered.txt").write_bytes(b"keep")
    result = runtime.run(job_id)
    assert result["state"] == "cleanup_failed"
    assert outside.read_bytes() == b"outside sentinel"
    if change in {"hash", "symlink"}:
        assert path.exists()
    if change == "unknown":
        assert (path.parent / "unregistered.txt").read_bytes() == b"keep"


def test_whole_pool_removes_neutral_anchor_but_retains_personal_history(
    unheld, environment
):
    (users, _, entries, _), records, version = unheld
    for entry, user in zip(entries, users):
        UserWatchHistory.objects.create(
            user=user,
            pool=version.pool,
            resource=entry.pool.resource,
            snapshot={"avid": "PUB-001", "source_title": f"history-{user.pk}"},
            last_watched_at=timezone.now(),
            media_kind="source",
        )
    release(entries[1], users[1])
    ResourcePoolEntry.objects.filter(pk=version.pool_id).update(
        gc_after=timezone.now() - timedelta(seconds=1)
    )
    ResourceVersion.objects.filter(pool_id=version.pool_id).update(
        gc_after=timezone.now() - timedelta(seconds=1)
    )
    job_id = records.enqueue(version.pool_id)["job_id"]
    runtime = ResourceReclaimer(records, GcFileStorage(environment[2]))
    assert runtime.run(job_id)["state"] == "completed"
    pool = ResourcePoolEntry.objects.get(pk=version.pool_id)
    assert pool.state == "reclaimed" and pool.resource_id is None
    assert UserWatchHistory.objects.count() == 2
    assert not UserWatchHistory.objects.exclude(resource__isnull=True).exists()
    assert not list(environment[2]["cover"].glob("versions/*/*"))


def test_unmapped_legacy_path_blocks_before_claim(unheld, environment):
    (users, _, entries, _), records, version = unheld
    release(entries[1], users[1])
    ResourcePoolEntry.objects.filter(pk=version.pool_id).update(
        gc_after=timezone.now() - timedelta(seconds=1)
    )
    ResourceVersion.objects.filter(pool_id=version.pool_id).update(
        gc_after=timezone.now() - timedelta(seconds=1)
    )
    job_id = records.enqueue(version.pool_id)["job_id"]
    legacy = environment[2]["cover"] / "PUB-001.html"
    legacy.write_bytes(b"unknown old asset")
    runtime = ResourceReclaimer(records, GcFileStorage(environment[2]))
    with pytest.raises(GcDeferred):
        runtime.run(job_id)
    assert ResourceGcJob.objects.get(pk=job_id).state == "queued"
    assert legacy.read_bytes() == b"unknown old asset"


def test_bounded_batches_remove_known_nested_directories_and_keep_state_until_done(
    unheld, environment
):
    import hashlib
    from uuid import uuid4

    _, records, version = unheld
    content = path_for(environment[2], version).read_bytes()
    relative = f"versions/{version.pk}/actors/avatar.jpg"
    avatar = environment[2]["avatar"] / relative
    avatar.parent.mkdir(parents=True)
    avatar.write_bytes(content)
    marker = uuid4()
    digest = hashlib.sha256(content).hexdigest()
    TaskAssetTarget.objects.create(
        root="avatar", relative_path=relative, marker=marker, sha256=digest
    )
    version.manifest.append(
        {
            "root": "avatar",
            "kind": "avatar",
            "path": relative,
            "size": len(content),
            "sha256": digest,
            "marker": str(marker),
        }
    )
    version.save(update_fields=["manifest"])
    runtime, job_id = engine(unheld, environment, batch_size=1)
    assert runtime.run(job_id)["state"] == "queued"
    version.refresh_from_db()
    assert version.state == "deleting"
    assert ResourceGcAsset.objects.filter(job_id=job_id, state="deleted").count() == 1
    assert runtime.run(job_id)["state"] == "completed"
    assert not avatar.parent.exists()


@pytest.mark.django_db(transaction=True)
def test_real_mp4_live_session_protects_then_closed_expired_pins_are_released(
    clip, environment
):
    from test_version_local_playback import session
    from nassav.playback import records as playback_records
    from nassav.resource_gc_records import DjangoGcRecords
    from nassav.resource_version_models import ResourceReadLease
    from nassav.viewing import record_view
    from test_version_publication import context, runtime as task_runtime
    from uuid import uuid4

    users, client, video, path = clip
    row = session(clip)
    record_view(row.pk, users[0].pk, client.session.session_key, 1, 1)
    _, _, _, assets = task_runtime(context(environment[1], users[0]), environment[2])
    from nassav.task_models import TaskJob

    for job in TaskJob.objects.all():
        assert assets.cleanup(str(job.pk))["cleanup_state"] == "completed"
    entry = UserLibraryEntry.objects.get(user=users[0])
    release(entry, users[0])
    past = timezone.now() - timedelta(seconds=1)
    ResourcePoolEntry.objects.filter(pk=video.pool_id).update(gc_after=past)
    ResourceVersion.objects.filter(pool_id=video.pool_id).update(gc_after=past)
    records = DjangoGcRecords()
    with pytest.raises(GcDeferred) as blocked:
        records.enqueue(video.pool_id)
    assert "playback_sessions" in blocked.value.reasons and path.exists()
    playback_records.close(
        row.pk, users[0].pk, client.session.session_key, row.version, uuid4()
    )
    ResourceReadLease.objects.create(
        user=users[0],
        version=video,
        playback_session=row,
        request_id=uuid4(),
        login_hash="fixture",
        expires_at=past,
        absolute_expires_at=past,
    )
    job_id = records.enqueue(video.pool_id)["job_id"]
    assert (
        ResourceReclaimer(records, GcFileStorage(environment[2])).run(job_id)["state"]
        == "completed"
    )
    assert not path.exists() and not ResourceReadLease.objects.exists()
    assert UserWatchHistory.objects.get(user=users[0]).resource_id is None


@pytest.mark.django_db(transaction=True)
def test_hash_runs_outside_db_and_only_checked_unlink_runs_inside_short_fence(
    unheld, environment, monkeypatch
):
    from contextlib import contextmanager
    from django.db import connection

    runtime, job_id = engine(unheld, environment)
    original = runtime.storage.deletion
    calls = []

    @contextmanager
    def checked(asset, check):
        assert not connection.in_atomic_block
        with original(asset, check) as (stamp, remove):
            assert not connection.in_atomic_block

            def unlink():
                assert connection.in_atomic_block
                calls.append(asset["pk"])
                remove()

            yield stamp, unlink

    monkeypatch.setattr(runtime.storage, "deletion", checked)
    assert runtime.run(job_id)["state"] == "completed"
    assert len(calls) == 1


@pytest.mark.parametrize("resume_delay", [0, 3600])
def test_expired_owner_cannot_unlink_even_after_file_was_verified(
    unheld, environment, resume_delay
):
    from nassav.resource_gc import GcLeaseLost

    _, records, version = unheld
    # Exercise protocol time explicitly. A host wall-clock rollback must not
    # accidentally make this test's manually expired lease valid again.
    clock = [version.gc_after + timedelta(seconds=1)]
    records.now = lambda: clock[0]
    storage = GcFileStorage(environment[2])
    job_id = records.enqueue(version.pool_id, version.pk)["job_id"]
    with storage.locked(records.intent(job_id)):
        token = records.claim(job_id)
        asset = records.assets(token)[0]
        with storage.deletion(asset, lambda: records.check(token)) as (stamp, remove):
            records.verified(token, asset["pk"], stamp)
            clock[0] = ResourceGcJob.objects.get(pk=job_id).lease_until + timedelta(
                microseconds=1
            )
            unlink = Mock(wraps=remove)
            with pytest.raises(GcLeaseLost):
                records.unlink(token, asset["pk"], unlink)
            unlink.assert_not_called()
        assert path_for(environment[2], version).exists()
    clock[0] += timedelta(seconds=resume_delay)
    result = ResourceReclaimer(records, storage).run(job_id)
    assert result["state"] == "completed", {
        "result": result,
        "lease_until": ResourceGcJob.objects.get(pk=job_id).lease_until,
        "now": records.now(),
    }
