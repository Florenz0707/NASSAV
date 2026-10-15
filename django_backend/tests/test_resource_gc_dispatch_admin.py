"""Audited admin commands and fair bounded broker recovery, on real databases."""

from datetime import timedelta
from uuid import uuid4, UUID
from unittest.mock import Mock

import pytest
from django.db import connection
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from nassav.resource_gc_dispatch import GcDispatcher
from nassav.resource_gc_admin import GcAdministration, GcAdminConflict
from nassav.resource_gc_admin_records import DjangoGcAdminCommands
from nassav.resource_gc_records import DjangoGcRecords
from nassav.resource_gc_models import ResourceGcJob
from nassav.resource_version_models import ResourceVersion, ResourceReadLease
from nassav.library_models import ResourcePoolEntry
from nassav.account_models import AuditEvent
from test_resource_gc_ledger import unheld as unheld
from test_version_source_playback import source_versions as source_versions
from test_version_publication import environment as environment

from test_session_lifecycle_contracts import isolated_redis as _isolated_redis

gc_redis = _isolated_redis
pytestmark = pytest.mark.django_db(transaction=True)


def command(version, **extra):
    return {
        "request_id": str(uuid4()),
        "reason": "maintenance",
        "expected_version": version,
        **extra,
    }


def test_audited_enqueue_replays_without_another_dispatch_and_hides_private_metadata(
    unheld,
):
    (users, _, _, _), records, version = unheld

    def send(job_id):
        assert not connection.in_atomic_block

    dispatch = Mock(side_effect=send)
    manager = GcAdministration(DjangoGcAdminCommands(records), dispatch)
    pool = ResourcePoolEntry.objects.get(pk=version.pool_id)
    payload = command(pool.version, version_id=str(version.pk))
    result = manager.execute(users[0].pk, "enqueue", pool.pk, payload)
    assert manager.execute(users[0].pk, "enqueue", pool.pk, payload) == result
    dispatch.assert_called_once_with(result["job_id"])
    audit = AuditEvent.objects.get(actor=users[0])
    assert audit.action == "gc_enqueue" and "private title" not in str(audit.result)
    with pytest.raises(GcAdminConflict):
        manager.execute(
            users[0].pk, "enqueue", pool.pk, {**payload, "reason": "security"}
        )
    with pytest.raises(PermissionError):
        manager.execute(
            users[1].pk,
            "enqueue",
            pool.pk,
            command(pool.version, version_id=str(version.pk)),
        )


def test_retention_and_failed_retry_are_versioned_and_audited(unheld):
    (users, _, _, _), records, version = unheld
    manager = GcAdministration(DjangoGcAdminCommands(records), Mock())
    pool = ResourcePoolEntry.objects.get(pk=version.pool_id)
    kept = manager.execute(
        users[0].pk, "retention", pool.pk, command(pool.version, retained=True)
    )
    assert kept["retained"] is True
    assert "admin_retention" in records.preview(pool.pk, version.pk)["blockers"]
    manager.execute(
        users[0].pk, "retention", pool.pk, command(kept["pool_version"], retained=False)
    )
    job_id = records.enqueue(pool.pk, version.pk)["job_id"]
    token = records.claim(job_id)
    failed = records.fail(token, "permission_denied")
    with pytest.raises(GcAdminConflict):
        manager.execute(users[0].pk, "retry", job_id, command(failed["revision"] - 1))
    assert (
        manager.execute(users[0].pk, "retry", job_id, command(failed["revision"]))[
            "state"
        ]
        == "queued"
    )


def test_recovery_cas_cooldown_and_broker_failure_are_bounded(unheld):
    _, records, version = unheld
    job_id = records.enqueue(version.pool_id, version.pk)["job_id"]
    now = records.now()
    ResourceGcJob.objects.filter(pk=job_id).update(
        updated_at=now - timedelta(seconds=61)
    )
    failing = Mock(side_effect=RuntimeError("broker unavailable"))
    dispatcher = GcDispatcher(records, failing, now=lambda: now)
    assert dispatcher.recover(1) == 0
    assert dispatcher.recover(1) == 0 and failing.call_count == 1
    assert ResourceGcJob.objects.get(pk=job_id).state == "queued"
    dispatcher.now = lambda: now + timedelta(seconds=61)
    dispatcher.send = Mock()
    assert dispatcher.recover(1) == 1
    assert dispatcher.recover(1) == 0


@pytest.mark.parametrize("scenario_offset", [-5, 0, 5])
def test_discovery_cursor_does_not_starve_after_a_protected_candidate(
    environment, scenario_offset
):
    users, _, _ = environment
    now = timezone.now() + timedelta(seconds=scenario_offset)
    records = DjangoGcRecords(now=lambda: now)
    versions = []
    for number in (1, 2):
        pool = ResourcePoolEntry.objects.create(
            canonical_avid=f"FAIR-{number}", state="ready"
        )
        versions.append(
            ResourceVersion.objects.create(
                id=UUID(int=number),
                pool=pool,
                pool_generation=1,
                kind="metadata",
                source_name="jable",
                access_scope="public",
                context_revision="fixture",
                state="ready",
                published_at=now,
                gc_after=now - timedelta(seconds=1),
            )
        )
    ResourceReadLease.objects.create(
        user=users[0],
        version=versions[0],
        request_id=uuid4(),
        login_hash="fixture",
        expires_at=now + timedelta(seconds=60),
        absolute_expires_at=now + timedelta(seconds=120),
    )
    dispatcher = GcDispatcher(records, Mock(), now=lambda: now)
    assert dispatcher.discover(1) == []
    found = dispatcher.discover(1)
    assert (
        len(found) == 1
        and ResourceGcJob.objects.get(pk=found[0]).version_id == versions[1].pk
    )


def test_http_preview_is_read_only_and_admin_commands_require_enabled_flag(
    unheld, monkeypatch
):
    (users, _, _, _), records, version = unheld
    manager = GcAdministration(DjangoGcAdminCommands(records), Mock())
    monkeypatch.setattr(
        "nassav.composition.build_resource_gc_administration", lambda: manager
    )
    client = APIClient()
    client.force_login(users[0])
    with override_settings(
        NASSAV_OPERATOR_USERNAME=users[0].username, RESOURCE_GC_ENABLED=False
    ):
        pool = ResourcePoolEntry.objects.get(pk=version.pool_id)
        url = f"/nassav/api/admin/resource-pools/{pool.pk}"
        response = client.get(url + "/gc-preview", {"version_id": str(version.pk)})
        assert response.status_code == 200 and response.data["data"]["eligible"] is True
        assert not ResourceGcJob.objects.exists()
        assert (
            client.post(
                url + "/gc",
                command(pool.version, version_id=str(version.pk)),
                format="json",
            ).status_code
            == 409
        )
        assert (
            client.get(
                f"/nassav/api/admin/resource-pools/{uuid4()}/gc-preview"
            ).status_code
            == 404
        )
    with override_settings(
        NASSAV_OPERATOR_USERNAME=users[0].username, RESOURCE_GC_ENABLED=True
    ):
        assert (
            client.post(
                url + "/gc",
                command(pool.version, version_id=str(version.pk)),
                format="json",
            ).status_code
            == 200
        )
    client.force_login(users[1])
    with override_settings(
        NASSAV_OPERATOR_USERNAME=users[1].username, RESOURCE_GC_ENABLED=True
    ):
        assert client.get("/nassav/api/admin/resource-gc-jobs").status_code == 403


def test_gc_task_stays_disabled_without_explicit_cutover(settings, monkeypatch):
    from nassav.resource_gc_tasks import resource_gc_task, recover_resource_gc

    builder = Mock()
    monkeypatch.setattr("nassav.composition.build_resource_reclaimer", builder)
    settings.RESOURCE_GC_ENABLED = False
    assert resource_gc_task.run(str(uuid4()))["state"] == "disabled"
    assert recover_resource_gc() == {"discovered": 0, "dispatched": 0}
    builder.assert_not_called()


@pytest.mark.parametrize(
    "name",
    [
        "check_resources_consistency",
        "check_videos_consistency",
        "check_actor_avatars_consistency",
    ],
)
def test_legacy_asset_maintenance_is_closed_in_shared_mode(environment, settings, name):
    from django.core.management import call_command
    from django.core.management.base import CommandError

    settings.SHARED_LIBRARY_ENABLED = True
    with pytest.raises(CommandError, match="旧布局"):
        call_command(name, "--apply")


def test_cli_preview_is_read_only_and_apply_requires_explicit_admin_cutover(
    unheld, settings
):
    import io
    import json
    from django.core.management import call_command
    from django.core.management.base import CommandError

    _, records, version = unheld
    output = io.StringIO()
    call_command(
        "resource_gc", target=version.pool_id, version_id=version.pk, stdout=output
    )
    assert (
        json.loads(output.getvalue())["eligible"] is True
    )  # A's unused version is independent of B's hold.
    assert not ResourceGcJob.objects.exists()
    settings.RESOURCE_GC_ENABLED = False
    with pytest.raises(CommandError, match="回收执行开关"):
        call_command(
            "resource_gc",
            action="enqueue",
            target=version.pool_id,
            version_id=version.pk,
        )


@pytest.fixture
def preserve_celery_apps():
    from celery import current_app
    from celery.contrib.testing.app import setup_default_app

    # start_worker changes both global apps even with set_as_current=False.
    # Use Celery's test helper to restore apps and finalizers on every exit.
    previous = current_app._get_current_object()
    with setup_default_app(previous):
        yield
    assert current_app._get_current_object() is previous


def test_real_redis_celery_worker_executes_http_admin_request_without_eager(
    unheld, environment, settings, monkeypatch, gc_redis, preserve_celery_apps
):
    from celery import Celery
    from celery.contrib.testing.worker import start_worker
    from nassav.resource_gc_tasks import resource_gc_task
    from test_resource_gc_files import path_for
    import time

    (users, _, _, _), records, version = unheld
    for kind, path in environment[2].items():
        setattr(settings, f"{kind.upper()}_DIR", path)
    settings.RESOURCE_GC_ENABLED = True
    settings.TASK_RECOVERY_ENABLED = False
    queue = "gc-" + uuid4().hex
    socket_path = gc_redis.connection_pool.connection_kwargs["path"]
    app = Celery(
        "nassav-gc-isolated",
        broker=f"redis+socket://{socket_path}",
        backend="cache+memory://",
        set_as_current=False,
    )
    app.conf.update(
        task_always_eager=False,
        worker_hijack_root_logger=False,
        task_default_queue=queue,
    )
    task = app.task(name="nassav.tasks.resource_gc_task", ignore_result=False)(
        resource_gc_task.run
    )
    task.ignore_result = False
    deliveries = []

    def dispatch(job_id):
        result = task.apply_async(args=(job_id,), queue=queue, ignore_result=False)
        deliveries.append(result)

    manager = GcAdministration(DjangoGcAdminCommands(records), dispatch)
    monkeypatch.setattr(
        "nassav.composition.build_resource_gc_administration", lambda: manager
    )
    client = APIClient()
    client.force_login(users[0])
    path = path_for(environment[2], version)
    assert path.exists() and app.conf.task_always_eager is False
    try:
        with start_worker(
            app,
            pool="solo",
            concurrency=1,
            perform_ping_check=False,
            queues=[queue],
            shutdown_timeout=10,
        ):
            with override_settings(NASSAV_OPERATOR_USERNAME=users[0].username):
                pool = ResourcePoolEntry.objects.get(pk=version.pool_id)
                response = client.post(
                    f"/nassav/api/admin/resource-pools/{pool.pk}/gc",
                    command(pool.version, version_id=str(version.pk)),
                    format="json",
                )
                assert response.status_code == 200
                job_id = response.data["data"]["job_id"]
            deadline = time.monotonic() + 15
            while ResourceGcJob.objects.get(pk=job_id).state not in {
                "completed",
                "cleanup_failed",
            }:
                if deliveries and deliveries[0].ready():
                    assert deliveries[0].get(timeout=1).get("state") == "completed", (
                        records.status(job_id)
                    )
                assert time.monotonic() < deadline, records.status(job_id)
                time.sleep(0.05)
            assert ResourceGcJob.objects.get(pk=job_id).state == "completed"
            assert not path.exists()
    finally:
        app.close()


def test_other_private_scope_work_cannot_permanently_hold_an_unused_version(
    unheld, environment
):
    from test_version_publication import context, runtime, operation
    from nassav.shared_work_models import SharedWork
    from nassav.task_models import TaskJob

    (users, vault, _, _), records, version = unheld
    scope = context(vault, users[1])
    _, _, operations, _ = runtime(scope, environment[2])
    request = operation(users[1], scope, operations, kind="download", action="download")
    work = SharedWork.objects.get(subscriptions__operation_id=request["operation_id"])
    TaskJob.objects.filter(pk=work.job_id).update(state="paused")
    preview = records.preview(version.pool_id, version.pk)
    assert preview["eligible"] is True, preview
    assert "memberships" in records.preview(version.pool_id)["blockers"]
