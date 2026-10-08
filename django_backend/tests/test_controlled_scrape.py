"""Real DB/filesystem boundaries with controlled source responses, no live websites."""

from collections import Counter
from dataclasses import asdict
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from PIL import Image

from nassav.controlled_scrape import ControlledScrape
from nassav.models import AVResource
from nassav.resource_data import AVDownloadInfo
from nassav.resource_persistence import DjangoResourcePersistence
from nassav.task_assets import TaskAssets, TaskAssetError
from nassav.task_models import TaskArtifact, TaskEvent
from nassav.task_records import DjangoTaskRecords
from nassav.task_resource_events import TaskResourceEvents, receive_once
from nassav.task_resource_persistence import TaskResourcePersistence, resource_revision


@pytest.fixture
def context(db, tmp_path):
    records = DjangoTaskRecords()
    user = get_user_model().objects.create_user(username="scrape-owner")
    roots = {kind: tmp_path / kind for kind in ("cover", "avatar", "video")}
    assets = TaskAssets(roots, records)
    calls = Counter()
    stop = {"stage": None, "action": "pause"}
    job, _ = records.create(
        "scrape",
        "SCRAPE-1",
        owner_id=user.pk,
        action="add",
        options={"source": "chosen"},
    )

    def request(action):
        current = records.get(job["job_id"])
        return records.request(
            job["job_id"],
            action,
            expected_version=current["version"],
            request_id=str(uuid4()),
            actor_id=user.pk,
        )

    def hit(stage):
        calls[stage] += 1
        if stop["stage"] == stage:
            stop["stage"] = None
            request(stop["action"])

    class Gateway:
        def source(self, avid, source, *, force=False):
            assert source == "chosen"
            hit("source")
            return {
                "info": asdict(
                    AVDownloadInfo(
                        avid=avid,
                        source="fixture",
                        m3u8="fixture",
                        source_title="source title",
                    )
                ),
                "source_name": "fixture",
            }, b"private html"

        def scrape(self, avid, *, force=False):
            hit("metadata")
            return {
                "metadata": {
                    "title": "resource name",
                    "actors": ["Actor A", "Actor B"],
                    "genres": ["genre"],
                },
                "scraped_by": "fixture",
            }

        @staticmethod
        def avatars(prepared):
            return [("Actor A", "a"), ("Actor B", "b")]

        def cover(self, prepared, path):
            Image.new("RGB", (2, 2)).save(path, "JPEG")
            hit("cover")
            return True

        def avatar(self, url, path):
            Image.new("RGB", (2, 2)).save(path, "JPEG")
            hit(f"avatar-{url}")
            return True

    def prepare(control):
        return Gateway()

    persistence = TaskResourcePersistence(DjangoResourcePersistence())

    def persist(token, data, base, action):
        hit("save")
        return persistence.save(token, data, base, action)

    def publish(event, avid, event_id):
        hit("event")
        assert receive_once(event_id, "fixture")

    events = TaskResourceEvents(tmp_path / "events", publish)
    runner = ControlledScrape(
        records, assets, prepare, resource_revision, persist, events
    )
    return runner, records, assets, job, request, calls, stop


@pytest.mark.parametrize(
    "phase", ["source", "metadata", "cover", "avatar-a", "avatar-b", "event"]
)
@pytest.mark.parametrize("action,state", [("pause", "paused"), ("cancel", "cancelled")])
def test_stop_each_phase_preserves_only_committed_resource(
    context, phase, action, state
):
    runner, records, assets, job, request, calls, stop = context
    stop.update(stage=phase, action=action)
    result = runner.run(job["job_id"], job["task_id"])
    assert result["state"] == state
    saved = phase == "event"
    assert AVResource.objects.filter(avid=job["avid"]).exists() == saved
    assert (assets.roots["cover"] / "SCRAPE-1.jpg").exists() == saved
    assert result["resource_saved"] == saved
    if action == "cancel":
        assert all(
            not (root / ".tasks" / job["job_id"]).exists()
            for root in assets.roots.values()
        )
    else:
        resumed = request("resume")
        result = runner.run(job["job_id"], resumed["task_id"])
        assert result["state"] == "succeeded"
        assert calls["save"] == 1
        assert calls["event"] == 1
        # A completed private image is reused even if pause preceded its stage checkpoint.
        if phase in {"cover", "avatar-a", "avatar-b"}:
            assert calls[phase] == 1
        assert result["cleanup_state"] == "completed"
    assert runner.run(job["job_id"], job["task_id"])["status"] == "ignored"


def test_cancel_refresh_preserves_existing_metadata_and_images(context):
    runner, records, assets, job, request, calls, stop = context
    old = AVResource.objects.create(
        avid=job["avid"], original_title="existing", metadata={"old": True}
    )
    from nassav.task_models import TaskJob

    TaskJob.objects.filter(pk=job["job_id"]).update(action="refresh")
    for root, filename in [
        ("cover", "SCRAPE-1.jpg"),
        ("avatar", "Actor A.jpg"),
        ("video", "SCRAPE-1.mp4"),
    ]:
        assets.roots[root].mkdir(parents=True, exist_ok=True)
        (assets.roots[root] / filename).write_bytes(b"old")
    stop.update(stage="avatar-a", action="cancel")
    assert runner.run(job["job_id"], job["task_id"])["state"] == "cancelled"
    old.refresh_from_db()
    assert old.original_title == "existing"
    for root, filename in [
        ("cover", "SCRAPE-1.jpg"),
        ("avatar", "Actor A.jpg"),
        ("video", "SCRAPE-1.mp4"),
    ]:
        assert (assets.roots[root] / filename).read_bytes() == b"old"
    assert calls["save"] == 0


def test_resource_changed_during_pause_rejects_old_snapshot_and_compensates_files(
    context,
):
    runner, records, assets, job, request, calls, stop = context
    stop.update(stage="cover")
    assert runner.run(job["job_id"], job["task_id"])["state"] == "paused"
    AVResource.objects.create(avid=job["avid"], original_title="newer update")
    resumed = request("resume")
    assert runner.run(job["job_id"], resumed["task_id"])["state"] == "failed"
    assert AVResource.objects.get(avid=job["avid"]).original_title == "newer update"
    assert not (assets.roots["cover"] / "SCRAPE-1.jpg").exists()
    assert TaskEvent.objects.count() == 0


def test_commit_failure_rolls_back_resource_relations_and_files(context):
    runner, records, assets, job, request, calls, stop = context
    original = runner.persist

    def fail(*args):
        original(*args)
        raise OSError("disk/database fixture failure")

    runner.persist = fail
    result = runner.run(job["job_id"], job["task_id"])
    assert result["state"] == "failed"
    assert not AVResource.objects.exists()
    assert not TaskEvent.objects.exists()
    assert not (assets.roots["avatar"] / "Actor A.jpg").exists()


def test_event_failure_remains_pending_and_retries_without_resource_reexecution(
    context,
):
    runner, records, assets, job, request, calls, stop = context
    publish = runner.events.publish
    runner.events.publish = lambda *args: (_ for _ in ()).throw(
        ConnectionError("event unavailable")
    )
    assert runner.run(job["job_id"], job["task_id"])["state"] == "succeeded"
    event = TaskEvent.objects.get()
    assert event.state == "pending"
    runner.events.publish = publish
    runner.events.flush(job["job_id"])
    runner.events.flush(job["job_id"])
    assert calls["save"] == calls["event"] == 1
    assert not receive_once(str(event.id), "fixture")


def test_completed_checkpoint_corruption_does_not_publish(context):
    runner, records, assets, job, request, calls, stop = context
    stop.update(stage="cover")
    runner.run(job["job_id"], job["task_id"])
    artifact = TaskArtifact.objects.get(job_id=job["job_id"], relative_path="cover.jpg")
    assert artifact.details["complete"]
    (assets.roots["cover"] / ".tasks" / job["job_id"] / "cover.jpg").write_bytes(
        b"corrupted"
    )
    resumed = request("resume")
    assert runner.run(job["job_id"], resumed["task_id"])["state"] == "failed"
    assert not AVResource.objects.exists()


def test_paused_private_file_read_requires_same_attempt(context):
    runner, records, assets, job, request, calls, stop = context
    token = records.claim(job["job_id"], job["task_id"])
    assets.stage(
        token,
        "cover",
        "page.html",
        "html",
        lambda path: bool(path.write_bytes(b"fixture")),
    )
    assert assets.read(token, "cover", "page.html") == b"fixture"
    with pytest.raises(TaskAssetError):
        assets.read(token, "cover", "missing")


@pytest.mark.parametrize("action,state", [("pause", "paused"), ("cancel", "cancelled")])
def test_control_before_commit_prevents_files_and_db(context, action, state):
    runner, records, assets, job, request, calls, stop = context

    def project(snapshot):
        if snapshot["stage"] == "saving":
            request(action)

    runner.project = project
    assert runner.run(job["job_id"], job["task_id"])["state"] == state
    assert not AVResource.objects.exists()
    assert calls["save"] == 0
    assert not (assets.roots["cover"] / "SCRAPE-1.jpg").exists()


def test_existing_valid_shared_avatar_is_preserved_without_download(context):
    runner, records, assets, job, request, calls, stop = context
    target = assets.roots["avatar"] / "Actor A.jpg"
    target.parent.mkdir()
    Image.new("RGB", (3, 3), color="blue").save(target, "JPEG")
    original = target.read_bytes()
    assert runner.run(job["job_id"], job["task_id"])["state"] == "succeeded"
    assert calls["avatar-a"] == 0
    assert target.read_bytes() == original


def test_partial_cover_failure_still_saves_metadata_and_never_promotes_bad_image(
    context,
):
    runner, records, assets, job, request, calls, stop = context
    factory = runner.preparation

    def preparation(control):
        gateway = factory(control)

        def cover(prepared, path):
            path.write_bytes(b"partial image")
            return False

        gateway.cover = cover
        return gateway

    runner.preparation = preparation
    result = runner.run(job["job_id"], job["task_id"])
    assert result["state"] == "succeeded"
    assert AVResource.objects.get().original_title == "resource name"
    assert not (assets.roots["cover"] / "SCRAPE-1.jpg").exists()
    assert result["cleanup_state"] == "completed"


def test_adapter_construction_failure_releases_active_reservation(context):
    runner, records, assets, job, request, calls, stop = context

    def preparation(control):
        raise ValueError("invalid fixture adapter configuration")

    runner.preparation = preparation
    assert runner.run(job["job_id"], job["task_id"])["state"] == "failed"
    replacement, duplicate = records.create(
        "scrape", job["avid"], owner_id=None, action="add"
    )
    assert not duplicate
    assert replacement["job_id"] != job["job_id"]


def test_warm_structured_source_commits_without_html_artifact(context):
    runner, records, assets, job, request, calls, stop = context
    preparation = runner.preparation

    def warm(control):
        gateway = preparation(control)
        original = gateway.source

        def source(avid, name, *, force=False):
            prepared, _ = original(avid, name, force=force)
            return prepared, None

        gateway.source = source
        return gateway

    runner.preparation = warm
    result = runner.run(job["job_id"], job["task_id"])
    assert result["state"] == "succeeded"
    assert AVResource.objects.filter(avid="SCRAPE-1").exists()
    assert not (assets.roots["cover"] / "SCRAPE-1.html").exists()
    assert (assets.roots["cover"] / "SCRAPE-1.jpg").exists()
