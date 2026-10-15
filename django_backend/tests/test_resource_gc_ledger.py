"""DB reclamation fences with real publications; no deletion adapter enabled yet."""

from datetime import timedelta
from dataclasses import replace
from uuid import uuid4

import pytest
from django.db import transaction, connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from nassav.resource_gc import GcDeferred, GcLeaseLost, GcEvidenceError
from nassav.resource_gc_records import DjangoGcRecords
from nassav.resource_gc_schedule import schedule_unused_versions
from nassav.resource_gc_models import ResourceGcJob, ResourceGcAsset
from nassav.resource_version_models import (
    ResourceVersion,
    ResourceVersionPointer,
    ResourceReadLease,
)
from nassav.library_models import ResourcePoolEntry
from nassav.library_records import DjangoMembershipRecords
from nassav.library_membership import LibraryMembership, LibraryConflict
from nassav.resource_deletion import (
    DjangoResourceDeletionRepository,
    ResourceTaskConflict,
)
from nassav.task_models import TaskJob, TaskAttempt, TaskArtifact
from nassav.shared_work_models import SharedWork
from nassav.playback import records as playback_records
from test_version_source_playback import source_versions as source_versions, submit
from test_version_publication import environment as environment, context, runtime

pytestmark = pytest.mark.django_db


@pytest.fixture
def unheld(source_versions, environment, monkeypatch):
    users, vault, entries, _ = source_versions
    for user, entry in zip(users, entries):
        _, _, _, assets = runtime(context(vault, user), environment[2])
        work = SharedWork.objects.get(pk=entry.current_version.work_id)
        assert assets.cleanup(str(work.job_id))["cleanup_state"] == "completed"
    # All GC adapters created by this scenario (including HTTP/CLI/worker
    # assembly) share one protocol clock. Other domains keep their own clocks.
    instant = timezone.now()
    original_init = DjangoGcRecords.__init__

    def controlled_init(self, *args, **kwargs):
        kwargs.setdefault("now", lambda: instant)
        original_init(self, *args, **kwargs)

    monkeypatch.setattr(DjangoGcRecords, "__init__", controlled_init)
    records = DjangoGcRecords()
    for entry in entries:
        entry.refresh_from_db()
    release(entries[0], users[0])
    version = entries[0].current_version
    ResourceVersion.objects.filter(pk=version.pk).update(
        gc_after=records.now() - timedelta(seconds=1)
    )
    version.refresh_from_db()
    return source_versions, records, version


def release(entry, user):
    entry.refresh_from_db()
    return LibraryMembership(DjangoMembershipRecords()).release(
        user.pk, entry.pk, expected_version=entry.version
    )


def test_private_unused_version_eligible_without_reclaiming_other_users_pool(unheld):
    (_, _, entries, _), records, version = unheld
    assert records.preview(version.pool_id, version.pk)["eligible"] is True
    pool_view = records.preview(version.pool_id)
    assert "memberships" in pool_view["blockers"]
    snapshot = records.enqueue(version.pool_id, version.pk)
    assert records.enqueue(version.pool_id, version.pk)["job_id"] == snapshot["job_id"]
    token = records.claim(snapshot["job_id"])
    assert token is not None
    version.refresh_from_db()
    entries[1].pool.refresh_from_db()
    entries[1].current_version.refresh_from_db()
    assert version.state == "deleting"
    assert (
        entries[1].pool.state == "ready" and entries[1].current_version.state == "ready"
    )
    assert ResourceGcAsset.objects.filter(job_id=token.job_id).count() == len(
        version.manifest
    )
    assert not ResourceVersionPointer.objects.filter(current=version).exists()
    assert not records.claim(token.job_id)
    records.check(token)
    with pytest.raises(GcLeaseLost):
        records.check(replace(token, owner=uuid4()))
    assert records.fail(token, "permission_denied")["state"] == "cleanup_failed"
    version.refresh_from_db()
    assert version.state == "cleanup_failed"
    assert "other_gc_pending" in records.preview(version.pool_id)["blockers"]
    resumed = records.claim(token.job_id)
    assert resumed.owner != token.owner
    version.refresh_from_db()
    assert version.state == "deleting"
    with pytest.raises(GcLeaseLost):
        records.check(token)


def test_read_pin_and_original_session_protect_after_ordinary_release(source_versions):
    users, _, entries, clients = source_versions
    row = submit(source_versions)
    row.state = "ready"
    row.save(update_fields=["state"])
    release(entries[0], users[0])
    version = entries[0].current_version
    now = timezone.now()
    records = DjangoGcRecords(now=lambda: now)
    ResourceVersion.objects.filter(pk=version.pk).update(
        gc_after=records.now() - timedelta(seconds=1)
    )
    ResourceReadLease.objects.create(
        user=users[0],
        version=version,
        request_id=uuid4(),
        login_hash="fixture",
        expires_at=now + timedelta(seconds=30),
        absolute_expires_at=now + timedelta(seconds=60),
    )
    preview = records.preview(version.pool_id, version.pk)
    assert {"read_leases", "playback_sessions"} <= set(preview["blockers"])
    playback_records.close(
        row.pk, users[0].pk, clients[0].session.session_key, row.version, uuid4()
    )
    assert (
        "playback_sessions"
        not in records.preview(version.pool_id, version.pk)["blockers"]
    )
    assert "read_leases" in records.preview(version.pool_id, version.pk)["blockers"]


def test_paused_unknown_writer_and_pending_recovery_never_become_eligible(unheld):
    (_, _, _, _), records, version = unheld
    job = TaskJob.objects.create(
        avid=version.pool.canonical_avid,
        kind="download",
        action="download",
        state="paused",
        active_key="gc-paused",
    )
    assert (
        "active_or_paused_task"
        in records.preview(version.pool_id, version.pk)["blockers"]
    )
    job.state, job.active_key = "failed", None
    job.save()
    TaskAttempt.objects.create(
        job=job,
        generation=1,
        state="running",
        started_at=timezone.now(),
        execution_identity={"worker_host": "old-container"},
    )
    assert (
        "writer_stop_unconfirmed"
        in records.preview(version.pool_id, version.pk)["blockers"]
    )
    TaskAttempt.objects.filter(job=job).update(
        state="stopped", stopped_at=timezone.now()
    )
    TaskArtifact.objects.create(
        job=job,
        root="video",
        relative_path="unknown.mp4",
        kind="video",
        state="promoting",
    )
    assert (
        "artifact_recovery_pending"
        in records.preview(version.pool_id, version.pk)["blockers"]
    )
    job.cleanup_state = "failed"
    job.save()
    assert (
        "task_cleanup_pending"
        in records.preview(version.pool_id, version.pk)["blockers"]
    )
    with pytest.raises(GcDeferred):
        records.enqueue(version.pool_id, version.pk)


def test_last_release_sets_grace_while_another_holder_preserves_shared_version(unheld):
    (users, _, entries, _), records, version = unheld
    now = records.now()
    first = ResourceVersion.objects.get(pk=version.pk).gc_after
    with transaction.atomic():
        schedule_unused_versions(version.pool, now=now + timedelta(hours=1))
    assert ResourceVersion.objects.get(pk=version.pk).gc_after == first
    assert (
        ResourceVersion.objects.get(pk=entries[1].current_version_id).gc_after is None
    )
    release(entries[1], users[1])
    pool = ResourcePoolEntry.objects.get(pk=version.pool_id)
    assert pool.state == "pending_gc" and pool.gc_after > now
    assert "grace_period" in records.preview(pool.pk)["blockers"]
    pool.retained = True
    pool.save()
    assert "admin_retention" in records.preview(pool.pk, version.pk)["blockers"]


def test_readd_invalidates_queued_whole_pool_claim_and_deleting_blocks_attach(unheld):
    (users, _, entries, _), records, version = unheld
    release(entries[1], users[1])
    ResourcePoolEntry.objects.filter(pk=version.pool_id).update(
        gc_after=records.now() - timedelta(seconds=1)
    )
    ResourceVersion.objects.filter(
        pool_id=version.pool_id, state__in=["ready", "retired"]
    ).update(gc_after=records.now() - timedelta(seconds=1))
    snapshot = records.enqueue(version.pool_id)
    LibraryMembership(DjangoMembershipRecords()).attach(
        users[1].pk, version.pool.canonical_avid, source="jable", access_scope="public"
    )
    assert records.claim(snapshot["job_id"]) is None
    assert ResourceGcJob.objects.get(pk=snapshot["job_id"]).state == "cancelled"
    # A version deletion does not invalidate unrelated B's new public generation.
    token = records.claim(records.enqueue(version.pool_id, version.pk)["job_id"])
    assert token is not None
    assert ResourcePoolEntry.objects.get(pk=version.pool_id).state == "ready"


def test_manifest_or_marker_failure_does_not_cut_pointer_or_make_files_public(unheld):
    _, records, version = unheld
    snapshot = records.enqueue(version.pool_id, version.pk)
    original = version.manifest
    version.manifest = [{**original[0], "path": "../outside.jpg"}]
    version.save(update_fields=["manifest"])
    with pytest.raises(GcEvidenceError):
        records.claim(snapshot["job_id"])
    assert ResourceGcJob.objects.get(pk=snapshot["job_id"]).state == "queued"
    assert not ResourceGcAsset.objects.exists()
    assert ResourceVersionPointer.objects.filter(current=version).exists()


def test_legacy_delete_cannot_bypass_shared_or_private_version_guards(unheld):
    _, _, version = unheld
    with pytest.raises(ResourceTaskConflict, match="共享资源"):
        DjangoResourceDeletionRepository().get(version.pool.canonical_avid)


@pytest.mark.django_db(transaction=True)
def test_gc_migration_roundtrip_and_refuse_discarding_gc_evidence():
    old = [("nassav", "0049_viewing_history_clock")]
    new = [("nassav", "0050_resource_gc_ledger")]
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    try:
        executor.migrate(old)
        apps = executor.loader.project_state(old).apps
        pool = apps.get_model("nassav", "ResourcePoolEntry").objects.create(
            canonical_avid="GC-049"
        )
        for _ in range(2):
            executor = MigrationExecutor(connection)
            executor.migrate(new)
            apps = executor.loader.project_state(new).apps
            row = apps.get_model("nassav", "ResourcePoolEntry").objects.get(pk=pool.pk)
            assert row.retained is False and row.lifetime_generation == 1
            assert not apps.get_model("nassav", "ResourceGcJob").objects.exists()
            executor = MigrationExecutor(connection)
            executor.migrate(old)
        executor = MigrationExecutor(connection)
        executor.migrate(new)
        apps = executor.loader.project_state(new).apps
        apps.get_model("nassav", "ResourceGcJob").objects.create(
            pool_id=pool.pk, pool_generation=1, active_key="fixture"
        )
        with pytest.raises(RuntimeError, match="restore backup"):
            MigrationExecutor(connection).migrate(old)
        assert (
            MigrationExecutor(connection)
            .loader.project_state(new)
            .apps.get_model("nassav", "ResourceGcJob")
            .objects.exists()
        )
    finally:
        MigrationExecutor(connection).migrate(latest)


@pytest.mark.django_db(transaction=True)
def test_pool_claim_racing_new_attach_is_linearizable(unheld):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from django.db import close_old_connections

    (users, _, entries, _), records, version = unheld
    release(entries[1], users[1])
    ResourcePoolEntry.objects.filter(pk=version.pool_id).update(
        gc_after=records.now() - timedelta(seconds=1)
    )
    ResourceVersion.objects.filter(
        pool_id=version.pool_id, state__in=["ready", "retired"]
    ).update(gc_after=records.now() - timedelta(seconds=1))
    job_id = records.enqueue(version.pool_id)["job_id"]
    barrier = Barrier(2)

    def reclaim():
        close_old_connections()
        try:
            barrier.wait()
            return records.claim(job_id)
        finally:
            close_old_connections()

    def attach():
        close_old_connections()
        try:
            barrier.wait()
            try:
                return LibraryMembership(DjangoMembershipRecords()).attach(
                    users[1].pk, "PUB-001", source="jable", access_scope="public"
                )
            except LibraryConflict as error:
                return error
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as workers:
        first, second = workers.submit(reclaim), workers.submit(attach)
        token, result = first.result(), second.result()
    assert (token is not None) == isinstance(result, LibraryConflict)
    pool = ResourcePoolEntry.objects.get(pk=version.pool_id)
    if token:
        assert pool.state == "deleting" and not pool.memberships.exists()
    else:
        assert pool.state == "ready" and pool.memberships.count() == 1
        assert ResourceGcJob.objects.get(pk=job_id).state == "cancelled"


def test_expired_gc_claim_cannot_renew_or_finish_and_new_owner_is_fenced(unheld):
    _, records, version = unheld
    job_id = records.enqueue(version.pool_id, version.pk)["job_id"]
    first = records.claim(job_id)
    ResourceGcJob.objects.filter(pk=job_id).update(
        lease_until=records.now() - timedelta(seconds=1)
    )
    with pytest.raises(GcLeaseLost):
        records.check(first)
    second = records.claim(job_id)
    assert second.owner != first.owner
    with pytest.raises(GcLeaseLost):
        records.fail(first, "permission_denied")
    records.check(second)
    assert ResourceGcAsset.objects.filter(job_id=job_id).count() == len(
        version.manifest
    )


def test_pool_deadline_cannot_override_a_later_version_grace(unheld):
    (users, _, entries, _), records, version = unheld
    release(entries[1], users[1])
    ResourcePoolEntry.objects.filter(pk=version.pool_id).update(
        gc_after=records.now() - timedelta(seconds=1)
    )
    assert "version_grace_period" in records.preview(version.pool_id)["blockers"]
    with pytest.raises(GcDeferred):
        records.enqueue(version.pool_id)


def test_claim_batch_checks_markers_without_per_file_queries(unheld):
    from django.test.utils import CaptureQueriesContext
    from nassav.task_models import TaskAssetTarget

    _, records, version = unheld
    manifest, targets = list(version.manifest), []
    for index in range(200):
        path = f"versions/{version.pk}/avatar-{index}.jpg"
        marker = uuid4()
        manifest.append(
            {
                "root": "avatar",
                "kind": "avatar",
                "path": path,
                "marker": str(marker),
                "sha256": "a" * 64,
                "size": 1,
            }
        )
        targets.append(
            TaskAssetTarget(
                root="avatar", relative_path=path, marker=marker, sha256="a" * 64
            )
        )
    TaskAssetTarget.objects.bulk_create(targets)
    ResourceVersion.objects.filter(pk=version.pk).update(manifest=manifest)
    job_id = records.enqueue(version.pool_id, version.pk)["job_id"]
    with CaptureQueriesContext(connection) as queries:
        token = records.claim(job_id)
    assert (
        token is not None
        and ResourceGcAsset.objects.filter(job_id=job_id).count() == 201
    )
    assert (
        sum(
            "SELECT" in item["sql"] and "nassav_task_asset_target" in item["sql"]
            for item in queries
        )
        == 1
    )


def test_live_owner_renews_before_deadline_but_cannot_renew_after_expiry(unheld):
    _, records, version = unheld
    clock = [records.now()]
    records.now = lambda: clock[0]
    job_id = records.enqueue(version.pool_id, version.pk)["job_id"]
    token = records.claim(job_id)
    initial = ResourceGcJob.objects.get(pk=job_id)
    clock[0] = initial.lease_until - timedelta(seconds=1)
    records.check(token)
    renewed = ResourceGcJob.objects.get(pk=job_id)
    assert renewed.lease_until > initial.lease_until
    assert renewed.owner == initial.owner
    clock[0] = renewed.lease_until + timedelta(microseconds=1)
    with pytest.raises(GcLeaseLost):
        records.check(token)
    assert ResourceGcJob.objects.get(pk=job_id).lease_until == renewed.lease_until
