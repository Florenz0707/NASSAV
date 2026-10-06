"""Parent/child control and translation ownership on isolated DB and assets."""

import pytest

from test_controlled_scrape import context as context
from nassav.controlled_translation import ControlledTranslation
from nassav.models import AVResource
from nassav.owned_translation import OwnedTranslation
from nassav.translation_adapters import DjangoTranslationRepository
from nassav.translation_requests import DjangoTranslationRequests
from nassav.translation_workflow import TitleTranslationUseCase


@pytest.fixture
def chain(context):
    main, records, assets, job, request, calls, stop = context

    def continuation(token):
        if records.get(token.job_id)["translation"].get("state") in {
            "completed",
            "skipped",
        }:
            return records.finish(token, "succeeded")
        return records.handoff_translation(token)

    main.continuation = continuation
    effect = [lambda: None]
    outcome = ["译文"]

    class Translator:
        def __init__(self, control):
            self.control = control

        def translate(self, text):
            calls["translate"] += 1
            effect[0]()
            self.control.check()
            if isinstance(outcome[0], Exception):
                raise outcome[0]
            return outcome[0]

    child = ControlledTranslation(records, assets, OwnedTranslation(), Translator)
    queued = main.run(job["job_id"], job["task_id"])
    assert queued["state"] == "queued"
    assert queued["resource_saved"]
    assert queued["translation"]["task_id"] != job["task_id"]
    return main, child, records, assets, job, queued, request, calls, effect, outcome


def test_child_success_finishes_whole_job_and_preserves_saved_resource(chain):
    main, child, records, assets, job, queued, request, calls, effect, outcome = chain
    result = child.run(job["job_id"], queued["task_id"])
    assert result["state"] == "succeeded"
    assert result["stage"] == "translation_completed"
    assert result["translation"]["state"] == "completed"
    assert result["cleanup_state"] == "completed"
    assert AVResource.objects.get(avid=job["avid"]).translated_title == "译文"
    assert calls["save"] == calls["event"] == calls["translate"] == 1
    assert child.run(job["job_id"], queued["task_id"])["status"] == "ignored"


@pytest.mark.parametrize("action,state", [("pause", "paused"), ("cancel", "cancelled")])
@pytest.mark.parametrize("running", [False, True])
def test_stop_child_queue_or_running_keeps_metadata_and_old_translation(
    chain, action, state, running
):
    main, child, records, assets, job, queued, request, calls, effect, outcome = chain
    AVResource.objects.filter(avid=job["avid"]).update(
        translated_title="old translation"
    )
    if running:
        effect[0] = lambda: request(action)
        result = child.run(job["job_id"], queued["task_id"])
    else:
        result = request(action)
        assert child.run(job["job_id"], queued["task_id"])["status"] == "ignored"
    assert result["state"] == state
    assert result["translation"]["state"] == state
    resource = AVResource.objects.get(avid=job["avid"])
    assert resource.original_title == "resource name"
    assert resource.translated_title == "old translation"
    assert resource.translation_status == "pending"
    assert (assets.roots["cover"] / "SCRAPE-1.jpg").exists()
    if action == "pause":
        effect[0] = lambda: None
        resumed = request("resume")
        new_child = main.run(job["job_id"], resumed["task_id"])
        assert new_child["translation"]["task_id"] != queued["task_id"]
        assert child.run(job["job_id"], new_child["task_id"])["state"] == "succeeded"
        assert calls["save"] == calls["event"] == 1


@pytest.mark.parametrize("outcome", [None, RuntimeError("fixture unavailable")])
def test_translation_failure_finishes_parent_without_undoing_resource(chain, outcome):
    main, child, records, assets, job, queued, request, calls, effect, result = chain
    result[0] = outcome
    snapshot = child.run(job["job_id"], queued["task_id"])
    assert snapshot["state"] == snapshot["translation"]["state"] == "failed"
    assert snapshot["resource_saved"]
    assert AVResource.objects.get(avid=job["avid"]).translation_status == "failed"


@pytest.mark.parametrize("when", ["queued", "running", "paused"])
def test_new_manual_translation_request_supersedes_parent_only(chain, when):
    main, child, records, assets, job, queued, request, calls, effect, outcome = chain

    def manual():
        DjangoTranslationRequests(lambda avid, generation: None).request(job["avid"])
        AVResource.objects.filter(avid=job["avid"]).update(
            translation_status="completed", translated_title="new manual result"
        )

    if when == "running":
        effect[0] = manual
    elif when == "paused":
        effect[0] = lambda: request("pause")
        assert child.run(job["job_id"], queued["task_id"])["state"] == "paused"
        manual()
        resumed = request("resume")
        queued = main.run(job["job_id"], resumed["task_id"])
        effect[0] = lambda: None
    else:
        manual()
    snapshot = child.run(job["job_id"], queued["task_id"])
    assert snapshot["error_code"] == "TRANSLATION_SUPERSEDED"
    resource = AVResource.objects.get(avid=job["avid"])
    assert resource.translation_status == "completed"
    assert resource.translated_title == "new manual result"


def test_stop_after_translation_commit_resume_does_not_translate_twice(chain):
    main, child, records, assets, job, queued, request, calls, effect, outcome = chain

    def project(snapshot):
        if snapshot["translation"].get("state") == "completed":
            request("pause")

    child.project = project
    assert child.run(job["job_id"], queued["task_id"])["state"] == "paused"
    resumed = request("resume")
    assert main.run(job["job_id"], resumed["task_id"])["state"] == "succeeded"
    assert calls["translate"] == calls["save"] == 1
    assert AVResource.objects.get(avid=job["avid"]).translated_title == "译文"


@pytest.mark.django_db
@pytest.mark.parametrize("batch", [False, True])
@pytest.mark.parametrize("throw", [False, True])
def test_old_manual_or_batch_success_and_failure_cannot_overwrite_new_request(
    batch, throw
):
    resource = AVResource.objects.create(
        avid="TR-CAS", original_title="title", translated_title="old"
    )

    class Translator:
        def translate(self, text):
            DjangoTranslationRequests(lambda avid, generation: None).request(
                resource.avid
            )
            AVResource.objects.filter(pk=resource.pk).update(
                translation_status="completed", translated_title="successor"
            )
            if throw:
                raise RuntimeError("old request failed")
            return "late result"

        def batch_translate(self, texts):
            return [self.translate(text) for text in texts]

    workflow = TitleTranslationUseCase(DjangoTranslationRepository(), Translator())
    result = (
        workflow.translate_batch([resource.avid])
        if batch
        else workflow.translate(resource.avid)
    )
    assert not result["success"]
    resource.refresh_from_db()
    assert resource.translation_status == "completed"
    assert resource.translated_title == "successor"


@pytest.mark.django_db
def test_queued_old_translation_is_rejected_before_translator_calls():
    resource = AVResource.objects.create(avid="TR-QUEUE", original_title="title")
    tickets = []
    requests = DjangoTranslationRequests(
        lambda avid, generation: tickets.append((avid, generation))
    )
    requests.request(resource.avid)
    requests.request(resource.avid)

    class Translator:
        def translate(self, text):
            pytest.fail("superseded queued task must not call translator")

    old_generation = tickets[0][1]
    workflow = TitleTranslationUseCase(
        DjangoTranslationRepository({resource.avid: old_generation}), Translator()
    )
    result = workflow.translate(resource.avid)
    assert result["translation_status"] == "superseded"
    resource.refresh_from_db()
    assert resource.translation_status == "pending"
    assert resource.translation_generation == tickets[1][1]


def test_wrong_worker_role_cannot_claim_child(chain):
    main, child, records, assets, job, queued, request, calls, effect, outcome = chain
    assert main.run(job["job_id"], queued["task_id"])["status"] == "ignored"
    assert records.get(job["job_id"])["state"] == "queued"
    assert child.run(job["job_id"], queued["task_id"])["state"] == "succeeded"


def test_retranslation_only_refresh_does_not_fetch_or_replace_metadata(context):
    from nassav.task_models import TaskJob

    main, records, assets, job, request, calls, stop = context
    resource = AVResource.objects.create(
        avid=job["avid"],
        original_title="existing title",
        translated_title="existing translation",
        metadata={"preserve": True},
        translation_status="completed",
    )
    stamp = resource.metadata_updated_at
    TaskJob.objects.filter(pk=job["job_id"]).update(
        action="refresh",
        options={"refresh_m3u8": False, "refresh_metadata": False, "retranslate": True},
    )
    main.existing = lambda avid: AVResource.objects.get(avid=avid)
    main.continuation = records.handoff_translation
    queued = main.run(job["job_id"], job["task_id"])
    assert queued["state"] == "queued"
    assert queued["stage"] == "translation_queued"
    resource.refresh_from_db()
    assert resource.metadata == {"preserve": True}
    assert resource.metadata_updated_at == stamp
    assert resource.translated_title == "existing translation"
    assert resource.translation_status == "completed"
    assert calls["source"] == calls["metadata"] == calls["cover"] == calls["save"] == 0
