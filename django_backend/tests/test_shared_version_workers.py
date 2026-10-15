"""Shared workflow integration with real DB/assets and injected network peers."""

from dataclasses import asdict
from types import SimpleNamespace
from uuid import uuid4

import pytest
from PIL import Image
from django.test import override_settings

from nassav.controlled_scrape import ControlledScrape
from nassav.resource_data import AVDownloadInfo
from nassav.resource_version_models import ResourceVersion, ResourceVersionPointer
from nassav.shared_work import SharedOperations
from nassav.shared_work_dispatch import dispatch_shared
from nassav.shared_work_tasks import execute_shared
from nassav.task_models import TaskJob, TaskAttempt
from nassav.task_records import DjangoTaskRecords
from nassav.versioned_task_publication import VersionedScrapePublication
from test_version_publication import (
    environment as environment,
    context,
    runtime,
    operation,
)

pytestmark = pytest.mark.django_db


def runner(
    environment,
    *,
    translate=lambda text: "translated fixture",
    on_source=lambda: None,
    action="add",
):
    users, vault, roots = environment
    ctx = context(vault)
    records, publications, operations, assets = runtime(ctx, roots)
    if action == "refresh":
        operations.manage_intents = True
    op = operation(users[0], ctx, operations, action=action)
    work_job = TaskJob.objects.get(
        shared_work__subscriptions__operation_id=op["operation_id"]
    )
    attempt = TaskAttempt.objects.get(job=work_job)
    policy = VersionedScrapePublication(
        records, publications, lambda control: SimpleNamespace(translate=translate)
    )

    class Gateway:
        def source(self, avid, source, *, force=False):
            on_source()
            return {
                "info": asdict(
                    AVDownloadInfo(
                        avid=avid,
                        source="Jable",
                        source_title="source fixture",
                        m3u8="https://fixture.invalid/stream.m3u8",
                    )
                ),
                "source_name": "Jable",
            }, b"private temporary html"

        def scrape(self, avid, *, force=False):
            return {
                "metadata": {
                    "title": "original fixture",
                    "actors": ["Actor fixture"],
                    "genres": ["Genre fixture"],
                },
                "scraped_by": "fixture",
            }

        def cover(self, prepared, path):
            Image.new("RGB", (4, 4)).save(path, "JPEG")
            return True

        def avatar(self, url, path):
            return self.cover({}, path)

        def avatars(self, prepared):
            return [("Actor fixture", "https://fixture.invalid/avatar.jpg")]

    workflow = ControlledScrape(
        records,
        assets,
        lambda control: Gateway(),
        lambda avid: None,
        policy.persist,
        SimpleNamespace(flush=lambda job: None),
        publication=policy,
    )
    return users, records, operations, workflow, op, work_job, attempt, roots


@pytest.mark.parametrize("legacy", [False, True])
@pytest.mark.parametrize("pause", [None, "queued", "source"])
def test_shared_refresh_uses_version_authority_and_survives_resume(
    environment, legacy, pause
):
    from nassav.library_models import ResourcePoolEntry, UserLibraryEntry
    from nassav.models import AVResource

    users = environment[0]
    old = None
    if legacy:
        resource = AVResource.objects.create(
            avid="PUB-001", original_title="legacy fixture"
        )
        pool = ResourcePoolEntry.objects.create(
            canonical_avid="PUB-001", resource=resource, state="ready"
        )
        UserLibraryEntry.objects.create(
            user=users[0],
            pool=pool,
            state="active",
            access_scope=f"legacy:operator:{users[0].pk}",
        )
    else:
        _, _, ops, initial, op, job, attempt, roots = runner(environment)
        assert initial.run(str(job.pk), str(attempt.pk))["state"] == "succeeded"
        ops.project(users[0].pk, op["operation_id"])
        old = ResourceVersion.objects.get(state="ready")
        old_metadata = dict(old.metadata)

    pause_source = [pause == "source"]

    def request(action):
        current = records.get(str(job.pk))
        return records.request(
            str(job.pk),
            action,
            expected_version=current["version"],
            request_id=str(uuid4()),
            actor_id=users[0].pk,
            allow_all=True,
        )

    def on_source():
        if pause_source[0]:
            pause_source[0] = False
            request("pause")

    _, records, ops, workflow, op, job, attempt, roots = runner(
        environment, action="refresh", on_source=on_source
    )
    if pause == "queued":
        assert request("pause")["state"] == "paused"
        resumed = request("resume")
        assert workflow.run(str(job.pk), str(attempt.pk))["status"] == "ignored"
        attempt = TaskAttempt.objects.get(job=job, generation=resumed["generation"])
    result = workflow.run(str(job.pk), str(attempt.pk))
    if pause == "source":
        assert result["state"] == "paused"
        if old is not None:
            assert ResourceVersionPointer.objects.get().current_id == old.pk
        resumed = request("resume")
        attempt = TaskAttempt.objects.get(job=job, generation=resumed["generation"])
        result = workflow.run(str(job.pk), str(attempt.pk))

    assert result["state"] == "succeeded", result.get("message")
    new = ResourceVersion.objects.get(work__job=job, state="ready")
    assert ops.project(users[0].pk, op["operation_id"])["state"] == "succeeded"
    assert UserLibraryEntry.objects.get(user=users[0]).current_version_id == new.pk
    assert (roots["cover"] / f"versions/{new.pk}/cover.jpg").is_file()
    if old is not None:
        old.refresh_from_db()
        assert old.metadata == old_metadata
        assert new.parent_id == old.pk
        assert (roots["cover"] / f"versions/{old.pk}/cover.jpg").is_file()
    else:
        assert new.parent_id is None
        resource.refresh_from_db()
        assert resource.original_title == "legacy fixture"


def test_shared_scrape_translates_before_atomic_publication_and_never_promotes_html(
    environment,
):
    users, records, operations, workflow, op, job, attempt, roots = runner(environment)
    result = workflow.run(str(job.pk), str(attempt.pk))
    assert (
        result["state"] == "succeeded" and result["translation"]["state"] == "completed"
    )
    version = ResourceVersion.objects.get(state="ready")
    assert version.metadata["translated_title"] == "translated fixture"
    assert version.metadata["translation_status"] == "completed"
    assert {asset["kind"] for asset in version.manifest} == {"cover", "avatar"}
    assert not any(asset["path"].endswith(".html") for asset in version.manifest)
    assert operations.project(users[0].pk, op["operation_id"])["state"] == "succeeded"
    assert (roots["cover"] / f"versions/{version.pk}/cover.jpg").exists()


def test_translation_failure_never_switches_pointer_or_reports_completion(environment):
    _, records, _, workflow, _, job, attempt, _ = runner(
        environment, translate=lambda text: None
    )
    result = workflow.run(str(job.pk), str(attempt.pk))
    assert result["state"] == "failed" and result["translation"]["state"] == "failed"
    assert ResourceVersion.objects.get().state == "staging"
    assert ResourceVersionPointer.objects.get().current_id is None
    assert records.get(str(job.pk))["cleanup_state"] == "completed"


def test_cancellation_during_source_keeps_no_published_version(environment):
    users, records, operations, workflow, op, job, attempt, _ = runner(environment)
    gateway_factory = workflow.preparation

    def prepare(control):
        gateway = gateway_factory(control)
        original = gateway.source

        def source(*args, **kwargs):
            SharedOperations(operations).cancel(
                users[0].pk, op["operation_id"], expected_version=1, request_id=uuid4()
            )
            control.check()
            return original(*args, **kwargs)

        gateway.source = source
        return gateway

    workflow.preparation = prepare
    result = workflow.run(str(job.pk), str(attempt.pk))
    assert result["state"] == "cancelled"
    assert not ResourceVersion.objects.filter(state="ready").exists()
    assert records.get(str(job.pk))["cleanup_state"] in {"not_required", "completed"}


def test_dispatch_uses_only_shared_ids_and_durable_retry(environment):
    _, _, _, _, _, shared, _, _ = runner(environment)
    legacy = DjangoTaskRecords()
    legacy.create("scrape", "LEGACY-001", owner_id=None, action="add")
    tickets = []
    with override_settings(SHARED_LIBRARY_ENABLED=True):
        assert dispatch_shared(
            sender=lambda ticket: (_ for _ in ()).throw(
                ConnectionError("broker unavailable")
            )
        ) == {"sent": 0, "failed": 1}
        assert TaskAttempt.objects.get(job=shared).state == "pending"
        assert dispatch_shared(sender=tickets.append) == {"sent": 1, "failed": 0}
    assert len(tickets) == 1 and tickets[0]["job_id"] == str(shared.pk)
    assert TaskAttempt.objects.get(job__avid="LEGACY-001").state == "pending"
    with override_settings(SHARED_LIBRARY_ENABLED=False):
        assert dispatch_shared(sender=tickets.append) == {"sent": 0, "failed": 0}


def test_unclaimed_source_setup_failure_ends_only_current_pending_delivery(environment):
    _, _, _, _, _, job, attempt, _ = runner(environment)
    with override_settings(SHARED_LIBRARY_ENABLED=True):
        result = execute_shared(
            str(job.pk),
            str(attempt.pk),
            builder=lambda job: (_ for _ in ()).throw(
                ValueError("invalid source setup")
            ),
        )
    assert result["status"] == "failed"
    job.refresh_from_db()
    attempt.refresh_from_db()
    assert job.state == attempt.state == "failed" and attempt.stopped_at is not None
    assert job.error_code == "SOURCE_CONTEXT_UNAVAILABLE"


def test_duplicate_delivery_cannot_fail_another_running_executor(environment):
    _, records, _, _, _, job, attempt, _ = runner(environment)
    records.claim(str(job.pk), str(attempt.pk))
    with override_settings(SHARED_LIBRARY_ENABLED=True):
        result = execute_shared(
            str(job.pk),
            str(attempt.pk),
            builder=lambda job: (_ for _ in ()).throw(
                ValueError("invalid duplicate setup")
            ),
        )
    assert result["status"] == "ignored"
    assert (
        TaskJob.objects.get().state == "running"
        and TaskAttempt.objects.get().state == "running"
    )


def test_shared_download_workflow_publishes_version_without_legacy_video_path(
    environment,
):
    from nassav.controlled_download import ControlledDownload
    from nassav.versioned_task_publication import VersionedDownloadPublication
    from test_controlled_download import Lease, Guard, Downloader
    from nassav.library_models import UserLibraryEntry

    users, records, operations, metadata_runner, op, job, attempt, roots = runner(
        environment
    )
    metadata_runner.run(str(job.pk), str(attempt.pk))
    operations.project(users[0].pk, op["operation_id"])
    vault = environment[1]
    ctx = context(vault)
    download_op = SharedOperations(operations).submit(
        users[0].pk,
        {
            "avid": "PUB-001",
            "source": "jable",
            "kind": "download",
            "action": "download",
            "request_id": str(uuid4()),
        },
        access_scope=ctx.work_binding["access_scope"],
        credential_refs=ctx.work_binding["credential_refs"],
        context_revision=ctx.work_binding["context_revision"],
    )
    work = TaskJob.objects.get(kind="download")
    attempt = TaskAttempt.objects.get(job=work)
    from nassav.resource_version_publication import VersionPublications
    from nassav.task_assets import TaskAssets

    publications = VersionPublications(records)
    policy = VersionedDownloadPublication(
        publications, ResourceVersion.objects.get(kind="metadata").metadata
    )
    workflow = ControlledDownload(
        records,
        TaskAssets(roots, records),
        SimpleNamespace(
            resolve=lambda avid, **kwargs: SimpleNamespace(
                info=SimpleNamespace(m3u8="https://fixture.invalid/index.m3u8"),
                domain="fixture.invalid",
            )
        ),
        Downloader(),
        Lease(),
        lambda avid: None,
        guard=Guard(),
        validate=lambda *args: True,
        publication=policy,
    )
    result = workflow.run(str(work.pk), str(attempt.pk))
    assert (
        result["status"] == "succeeded" and result["snapshot"]["state"] == "succeeded"
    )
    operations.project(users[0].pk, download_op["operation_id"])
    video = ResourceVersion.objects.get(kind="video")
    assert UserLibraryEntry.objects.get(user=users[0]).video_version_id == video.pk
    assert (roots["video"] / f"versions/{video.pk}/video.mp4").exists()
    assert not (roots["video"] / "PUB-001.mp4").exists()


def test_task_wrapper_is_registered_and_uses_only_business_id():
    from nassav.shared_work_tasks import shared_work_task

    assert shared_work_task.name == "nassav.tasks.shared_work_task"


def test_worker_result_never_returns_internal_checkpoints_or_source_links():
    result = {"state": "succeeded", "checkpoint": {"m3u8": "private fixture URL"}}
    workflow = SimpleNamespace(run=lambda job, attempt: result)
    with override_settings(SHARED_LIBRARY_ENABLED=True):
        output = execute_shared(
            str(uuid4()), str(uuid4()), builder=lambda job: workflow
        )
    assert set(output) == {"status", "job_id"}
    assert output["status"] == "succeeded"


def test_transport_cleanup_continues_after_one_close_fails():
    from unittest.mock import Mock
    from nassav.shared_worker_resources import WorkflowResources

    first = Mock()
    last = Mock(side_effect=RuntimeError("close failed fixture"))
    workflow = SimpleNamespace(run=lambda job, attempt: {"state": "failed"})
    assert WorkflowResources(workflow, [first, last]).run("fixture", "fixture") == {
        "state": "failed"
    }
    first.assert_called_once()
    last.assert_called_once()


def test_production_builder_uses_independent_sources_and_global_scraper_proxy(
    environment, monkeypatch
):
    from unittest.mock import Mock
    from nassav import composition
    from nassav.task_network import TaskNetworkControl

    _, _, _, _, _, job, _, _ = runner(environment)
    vault = environment[1]
    made = []

    class Source:
        def __init__(self):
            self.credential_context = context(vault)
            self.page_fetcher = None
            self.task_control = None
            made.append(self)

        def get_source_name(self):
            return "Jable"

        def bind_credential_context(self, ctx):
            self.credential_context = ctx

        def set_task_control(self, control):
            self.task_control = control

    factories = Mock(return_value={"jable": Source})
    scrapers = Mock(return_value=SimpleNamespace(get_scrapers=lambda: []))
    monkeypatch.setattr(composition, "source_factories", factories)
    from importlib import import_module

    manager_module = import_module("nassav.scraper.ScraperManager")
    monkeypatch.setattr(manager_module, "ScraperManager", scrapers)
    with override_settings(
        SHARED_LIBRARY_ENABLED=True,
        SOURCE_CREDENTIALS_ENABLED=True,
        PROXY_ENABLED=True,
        PROXY_URL="http://fixture-proxy.invalid:8080",
    ):
        workflow = composition.build_shared_workflow(str(job.pk))
        try:
            gateway = workflow.workflow.preparation(TaskNetworkControl(lambda: None))
            selected = gateway.sources.get_source("jable")
            template = next(
                source
                for source in made
                if source.credential_context is workflow.workflow.records.source_context
            )
            assert selected is not template and selected in made
            assert selected.credential_context is not template.credential_context
            assert (
                selected.credential_context.work_binding
                == template.credential_context.work_binding
            )
            assert factories.call_args.args[0] == "http://fixture-proxy.invalid:8080"
            assert scrapers.call_args.args[0] == "http://fixture-proxy.invalid:8080"
            assert template.task_control is None
        finally:
            workflow.close()
