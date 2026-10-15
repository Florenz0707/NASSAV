"""Real broker/solo worker and recovery CLI; synthetic source I/O only."""

from dataclasses import asdict
from io import StringIO
from threading import Event
from types import SimpleNamespace
from uuid import uuid4

import pytest
from celery import Celery
from celery.contrib.testing.worker import start_worker
from django.core.management import call_command
from django.contrib.sessions.models import Session
from PIL import Image

from nassav import composition
from nassav.account_models import UserAccount, UserLoginSession, AuditEvent
from nassav.controlled_scrape import ControlledScrape
from nassav.library_models import UserLibraryEntry
from nassav.library_submission import LibrarySubmission
from nassav.models import AVResource
from nassav.resource_data import AVDownloadInfo
from nassav.resource_version_models import ResourceVersion
from nassav.shared_work_dispatch import dispatch_shared
from nassav.shared_work_models import SharedWork
from nassav.shared_work_tasks import execute_shared
from nassav.task_models import TaskJob
from nassav.versioned_task_publication import VersionedScrapePublication
from test_library_commands_quota import managed
from test_multi_user_admission import browser
from test_version_publication import environment as environment
from test_resource_gc_dispatch_admin import preserve_celery_apps as preserve_celery_apps

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.mark.parametrize("cancel_count", [0, 1, 2])
def test_real_broker_worker_publishes_once_for_remaining_demand(
    environment, settings, monkeypatch, broker_redis, preserve_celery_apps, cancel_count
):
    settings.MULTI_USER_ENABLED = True
    settings.SHARED_LIBRARY_ENABLED = True
    settings.SOURCE_CREDENTIALS_ENABLED = True
    settings.TASK_RECOVERY_ENABLED = False
    users, ctx, tasks, publications, operations, assets = managed(environment)
    entered, release = Event(), Event()
    queue = "shared-acceptance-" + uuid4().hex
    socket_path = broker_redis.connection_pool.connection_kwargs["path"]
    app = Celery(
        "nassav-shared-acceptance",
        broker=f"redis+socket://{socket_path}",
        backend="cache+memory://",
        set_as_current=False,
    )
    app.conf.update(
        task_always_eager=False,
        worker_hijack_root_logger=False,
        task_default_queue=queue,
    )

    class Gateway:
        def __init__(self, control):
            self.control = control

        def source(self, avid, source, *, force=False):
            entered.set()
            assert release.wait(15), "Main test never released source barrier"
            self.control.check()
            return {
                "info": asdict(
                    AVDownloadInfo(
                        avid=avid,
                        source="Jable",
                        source_title=avid,
                        m3u8="https://fixture.invalid/test.m3u8",
                    )
                ),
                "source_name": "Jable",
            }, b"temporary synthetic source HTML"

        def scrape(self, avid, *, force=False):
            return {
                "metadata": {"title": avid, "actors": [], "genres": []},
                "scraped_by": "isolated-fixture",
            }

        def cover(self, prepared, path):
            Image.new("RGB", (4, 4)).save(path, "JPEG")
            return True

        def avatars(self, prepared):
            return []

    builds = []

    def build(job_id):
        builds.append(job_id)
        policy = VersionedScrapePublication(tasks, publications, lambda control: None)
        return ControlledScrape(
            tasks,
            assets,
            Gateway,
            lambda avid: None,
            policy.persist,
            SimpleNamespace(flush=lambda job: None),
            publication=policy,
        )

    completed_deliveries, duplicate_completed = [], Event()

    @app.task(bind=True, name="nassav.tasks.shared_work_task", ignore_result=False)
    def delivery(self, job_id):
        result = execute_shared(job_id, self.request.id, builder=build)
        completed_deliveries.append(result)
        if len(completed_deliveries) == 2:
            duplicate_completed.set()
        return result

    deliveries = []

    def send(ticket):
        deliveries.append(
            delivery.apply_async(
                args=(ticket["job_id"],), task_id=ticket["task_id"], queue=queue
            )
        )

    submission = LibrarySubmission(
        operations,
        lambda user, source, mode: (ctx, lambda: None),
        lambda: dispatch_shared(tasks, sender=send),
    )
    monkeypatch.setattr(composition, "build_library_submission", lambda: submission)
    monkeypatch.setattr(composition, "build_operation_records", lambda: operations)
    clients = [browser(user)[0] for user in users]
    requests = []
    for client in clients:
        response = client.post(
            "/nassav/api/library/entries",
            {
                "avid": "BROKER-001",
                "source": "jable",
                "credential_mode": "public",
                "request_id": str(uuid4()),
            },
            format="json",
        )
        assert response.status_code == 202, response.data
        requests.append(response.data["data"]["operation"])
    assert len(deliveries) == 1 and SharedWork.objects.count() == 1
    assert app.conf.task_always_eager is False
    try:
        with start_worker(
            app,
            pool="solo",
            concurrency=1,
            perform_ping_check=False,
            queues=[queue],
            shutdown_timeout=15,
        ):
            assert entered.wait(15), "Broker delivery never reached source barrier"
            assert TaskJob.objects.get().state == "running"
            for client, op in zip(clients[:cancel_count], requests):
                path = f"/nassav/api/my-operations/{op['operation_id']}"
                current = client.get(path).data["data"]
                cancelled = client.post(
                    path + "/cancel",
                    {
                        "expected_version": current["version"],
                        "request_id": str(uuid4()),
                    },
                    format="json",
                )
                assert cancelled.status_code == 200, cancelled.data
            release.set()
            result = deliveries[0].get(timeout=20, interval=0.05)
            assert result["status"] == (
                "cancelled" if cancel_count == 2 else "succeeded"
            )
            for index, (user, op) in enumerate(zip(users, requests)):
                snapshot = operations.project(user.pk, op["operation_id"])
                assert snapshot["state"] == (
                    "cancelled" if index < cancel_count else "succeeded"
                )
            ready = ResourceVersion.objects.filter(state="ready")
            if cancel_count == 2:
                assert not ready.exists()
                assert tasks.get(str(TaskJob.objects.get().pk))["cleanup_state"] in {
                    "not_required",
                    "completed",
                }
            else:
                version = ready.get()
                entries = UserLibraryEntry.objects.filter(state="active")
                assert entries.count() == 2 - cancel_count
                assert {entry.current_version_id for entry in entries} == {version.pk}
                assert (
                    environment[2]["cover"] / f"versions/{version.pk}/cover.jpg"
                ).is_file()
                assert not AVResource.objects.get().source_title
                assert not AVResource.objects.get().m3u8
            # Same message after completion must never publish another version.
            before = list(ResourceVersion.objects.values_list("pk", "state"))
            delivery.apply_async(
                args=(result["job_id"],), task_id=deliveries[0].id, queue=queue
            )
            # Reused Celery task ID may return its old backend result immediately.
            # Observe the actual second invocation, never that cached AsyncResult.
            assert duplicate_completed.wait(15), "Duplicate never reached real worker"
            assert completed_deliveries[1]["status"] == "ignored"
            assert list(ResourceVersion.objects.values_list("pk", "state")) == before
    finally:
        release.set()
        app.close()


def test_bootstrap_recovers_missing_admin_without_replaying_session_revocation(
    operator_user, settings
):
    settings.MULTI_USER_ENABLED = True
    settings.SHARED_LIBRARY_ENABLED = True
    settings.SOURCE_CREDENTIALS_ENABLED = True
    # Controlled corruption simulation in a disposable DB, never an HTTP role bypass.
    role = UserAccount.objects.create(user=operator_user, role="user")
    old, _ = browser(operator_user)
    old_key = old.session.session_key
    UserLoginSession.objects.create(user=operator_user, session_id=old_key)
    preview = StringIO()
    call_command("bootstrap_app_admin", username=operator_user.username, stdout=preview)
    role.refresh_from_db()
    assert '"applied": false' in preview.getvalue() and role.role == "user"
    assert Session.objects.filter(session_key=old_key).exists()
    request_id = str(uuid4())
    call_command(
        "bootstrap_app_admin",
        username=operator_user.username,
        apply=True,
        request_id=request_id,
        stdout=StringIO(),
    )
    role.refresh_from_db()
    assert role.role == "admin" and role.version == 2
    assert not Session.objects.filter(session_key=old_key).exists()
    assert old.get("/nassav/api/setting").status_code == 401
    fresh, snapshot = browser(operator_user)
    assert snapshot["capabilities"]["app_admin"] is True
    fresh_key = fresh.session.session_key
    UserLoginSession.objects.create(user=operator_user, session_id=fresh_key)
    call_command(
        "bootstrap_app_admin",
        username=operator_user.username,
        apply=True,
        request_id=request_id,
        stdout=StringIO(),
    )
    assert Session.objects.filter(session_key=fresh_key).exists()
    assert fresh.get("/nassav/api/setting").status_code == 200
    assert AuditEvent.objects.filter(action="account.bootstrap").count() == 1
