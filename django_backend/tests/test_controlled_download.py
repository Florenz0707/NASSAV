"""Controlled runner contracts use real DB/files and injectable media adapters."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model

from nassav.controlled_download import ControlledDownload
from nassav.download_contracts import DownloadLeaseLost
from nassav.download_resume import DownloadRestartRequired, HLSResumeGuard
from nassav.task_assets import TaskAssets
from nassav.task_models import TaskArtifact
from nassav.task_records import DjangoTaskRecords
from test_session_lifecycle_contracts import isolated_redis as isolated_redis


class Lease:
    def recovery_identity(self):
        return {}

    def __init__(self):
        self.slot = False
        self.closed = False
        self.available = True
        self.lost = False

    def start(self):
        pass

    def check(self):
        if self.lost:
            raise DownloadLeaseLost("test lease lost")

    def acquire_global(self):
        self.slot = self.available
        return self.slot

    def close(self):
        self.slot = False
        self.closed = True

    def retain_for_recovery(self):
        self.retained = True


class Downloader:
    def __init__(self):
        self.action = lambda **kwargs: None
        self.called = 0

    def download(self, **kwargs):
        self.called += 1
        self.action(**kwargs)
        if kwargs["cancelled"]():
            return False
        (kwargs["output_dir"] / f"{kwargs['output_name']}.mp4").write_bytes(
            b"full video"
        )
        return True

    def ensure_mp4(self, directory, name):
        return directory / f"{name}.mp4"


class Guard:
    def describe(self, *args):
        return {
            "safe": True,
            "url": "https://offline.invalid/index.m3u8",
            "identity": "fixture",
            "duration": 2,
            "urls": [],
        }

    def prepare(self, *args):
        pass

    def snapshot(self, *args):
        return {}


@pytest.fixture
def context(db, tmp_path):
    records = DjangoTaskRecords()
    owner = get_user_model().objects.create_user(username="download-control")
    job, _ = records.create("download", "DL-1", owner_id=owner.pk, action="download")
    assets = TaskAssets(
        {kind: tmp_path / kind for kind in ["cover", "avatar", "video"]}, records
    )
    resolver = SimpleNamespace(
        resolve=lambda avid, **kwargs: SimpleNamespace(
            info=SimpleNamespace(m3u8="https://offline.invalid/index.m3u8"),
            domain="offline.invalid",
        )
    )
    downloader, lease, saved, guard = Downloader(), Lease(), [], Guard()
    runner = ControlledDownload(
        records,
        assets,
        resolver,
        downloader,
        lease,
        saved.append,
        guard=guard,
        validate=lambda *args: True,
        sleep=lambda seconds: None,
    )
    return SimpleNamespace(
        records=records,
        owner=owner,
        job=job,
        assets=assets,
        runner=runner,
        downloader=downloader,
        lease=lease,
        saved=saved,
        guard=guard,
    )


def request(ctx, action):
    current = ctx.records.get(ctx.job["job_id"])
    return ctx.records.request(
        ctx.job["job_id"],
        action,
        expected_version=current["version"],
        request_id=str(uuid4()),
        actor_id=ctx.owner.pk,
    )


def execute(ctx, job=None):
    job = job or ctx.job
    return ctx.runner.run(job["job_id"], job["task_id"])


def test_success_publishes_then_cleans_private_workspace(context):
    ctx = context
    assert execute(ctx)["status"] == "succeeded"
    assert ctx.saved == ["DL-1"]
    assert (ctx.assets.roots["video"] / "DL-1.mp4").read_bytes() == b"full video"
    assert ctx.records.get(ctx.job["job_id"])["checkpoint"]["video_committed"]
    assert ctx.lease.closed and not ctx.lease.slot
    assert not (ctx.assets.roots["video"] / ".tasks" / ctx.job["job_id"]).exists()
    assert execute(ctx)["status"] == "ignored"


@pytest.mark.parametrize("action,state", [("pause", "paused"), ("cancel", "cancelled")])
def test_running_stop_keeps_existing_video_and_releases_slot(context, action, state):
    ctx = context
    existing = ctx.assets.roots["video"] / "DL-1.mp4"
    existing.parent.mkdir()
    existing.write_bytes(b"existing")

    def stop(**kwargs):
        path = kwargs["output_dir"] / "partial.ts"
        path.write_bytes(b"private partial")
        request(ctx, action)

    ctx.downloader.action = stop
    assert execute(ctx)["status"] == state
    assert not ctx.saved
    assert existing.read_bytes() == b"existing"
    private = ctx.assets.roots["video"] / ".tasks" / ctx.job["job_id"]
    assert private.exists() == (action == "pause")
    assert ctx.lease.closed and not ctx.lease.slot
    if action == "pause":
        ctx.downloader.action = lambda **kwargs: None
        resumed = request(ctx, "resume")
        assert execute(ctx, resumed)["status"] == "succeeded"
        assert ctx.saved == ["DL-1"]


def test_waiting_for_slot_can_pause_without_invoking_cli(context):
    ctx = context
    ctx.lease.available = False
    ctx.runner.sleep = lambda seconds: request(ctx, "pause")
    assert execute(ctx)["status"] == "paused"
    assert ctx.downloader.called == 0
    assert ctx.lease.closed


def test_stop_after_source_resolution_blocks_download(context):
    ctx = context
    old = ctx.runner.resolver.resolve

    def resolve(avid, **kwargs):
        request(ctx, "cancel")
        return old(avid)

    ctx.runner.resolver.resolve = resolve
    assert execute(ctx)["status"] == "cancelled"
    assert ctx.downloader.called == 0


def test_cancel_during_video_validation_cannot_publish(context):
    ctx = context

    def validate(*args):
        request(ctx, "cancel")
        args[2]()

    ctx.runner.validate = validate
    assert execute(ctx)["status"] == "cancelled"
    assert not ctx.saved
    assert not (ctx.assets.roots["video"] / "DL-1.mp4").exists()


def test_stop_after_commit_keeps_video_and_resume_skips_downloader(
    context, monkeypatch
):
    ctx = context
    original = ctx.assets.commit

    def commit(*args, **kwargs):
        result = original(*args, **kwargs)
        request(ctx, "pause")
        return result

    monkeypatch.setattr(ctx.assets, "commit", commit)
    assert execute(ctx)["status"] == "paused"
    resumed = request(ctx, "resume")
    assert execute(ctx, resumed)["status"] == "succeeded"
    assert ctx.saved == ["DL-1"]
    assert ctx.downloader.called == 1


def test_lost_lease_blocks_publication_and_preserves_existing_video(context):
    ctx = context
    existing = ctx.assets.roots["video"] / "DL-1.mp4"
    existing.parent.mkdir()
    existing.write_bytes(b"existing")
    ctx.downloader.action = lambda **kwargs: setattr(ctx.lease, "lost", True)
    result = execute(ctx)
    assert result["status"] == "failed"
    assert result["snapshot"]["error_code"] == "LEASE_LOST"
    assert not ctx.saved
    assert existing.read_bytes() == b"existing"


def test_unverifiable_resume_stays_paused_requires_explicit_restart(context):
    ctx = context

    def reject(*args):
        raise DownloadRestartRequired("content changed")

    ctx.guard.prepare = reject
    result = execute(ctx)
    assert result["status"] == "paused"
    assert result["snapshot"]["error_code"] == "RESTART_REQUIRED"
    assert ctx.downloader.called == 0


def test_persist_failure_restores_existing_video(context):
    ctx = context
    existing = ctx.assets.roots["video"] / "DL-1.mp4"
    existing.parent.mkdir()
    existing.write_bytes(b"existing")

    def fail(avid):
        raise RuntimeError("DB unavailable")

    ctx.runner.persist = fail
    assert execute(ctx)["status"] == "failed"
    assert existing.read_bytes() == b"existing"
    assert TaskArtifact.objects.get(kind="video").state == "deleted"


def test_resume_many_segments_uses_local_hash_and_cleans_incomplete_cache(tmp_path):
    def forbidden_fetch(*args):
        pytest.fail("resume must not download cached segment bytes")

    guard = HLSResumeGuard(fetch=forbidden_fetch)
    directory = tmp_path / "temp/DL-1/track"
    directory.mkdir(parents=True)
    for index in range(320):
        (directory / f"{index}.ts").write_bytes(f"valid-{index}".encode())
    manifest = {
        "safe": True,
        "identity": "same",
        "urls": [f"https://offline.invalid/{i}.ts" for i in range(321)],
    }
    checkpoint = {"manifest": manifest, "segments": guard.snapshot(tmp_path, "DL-1")}
    (directory / "2.ts").write_bytes(b"damaged")
    (directory / "3.ts").unlink()
    (directory / "320.ts").write_bytes(b"unrecorded")
    (directory / "321.ts.tmp").write_bytes(b"partial")
    checks = []
    guard.prepare(tmp_path, "DL-1", manifest, checkpoint, {}, lambda: checks.append(1))
    assert len(list(directory.glob("*"))) == 318
    assert (directory / "0.ts").read_bytes() == b"valid-0"
    assert not (directory / "2.ts").exists()
    assert not (directory / "320.ts").exists()
    assert not (directory / "321.ts.tmp").exists()
    assert len(checks) >= 320


def test_aes_resume_checks_current_key_identity_without_segment_download(tmp_path):
    key = b"0123456789abcdef"
    playlist = b'#EXTM3U\n#EXT-X-KEY:METHOD=AES-128,URI="key"\n#EXTINF:2,\nsegment.ts\n#EXT-X-ENDLIST\n'
    data = {
        "https://offline.invalid/index.m3u8": playlist,
        "https://offline.invalid/key": key,
    }
    calls = []

    def fetch(url, *_):
        calls.append(url)
        return data[url]

    guard = HLSResumeGuard(fetch=fetch)
    manifest = guard.describe("https://offline.invalid/index.m3u8", {}, lambda: None)
    file = tmp_path / "temp/DL-1/track/0.ts"
    file.parent.mkdir(parents=True)
    file.write_bytes(b"decrypted complete transport stream")
    checkpoint = {"manifest": manifest, "segments": guard.snapshot(tmp_path, "DL-1")}
    current = guard.describe("https://offline.invalid/index.m3u8", {}, lambda: None)
    guard.prepare(tmp_path, "DL-1", current, checkpoint, {}, lambda: None)
    assert file.exists()
    assert all(not url.endswith(".ts") for url in calls)
    data["https://offline.invalid/key"] = b"fedcba9876543210"
    changed = guard.describe("https://offline.invalid/index.m3u8", {}, lambda: None)
    with pytest.raises(DownloadRestartRequired):
        guard.prepare(tmp_path, "DL-1", changed, checkpoint, {}, lambda: None)
    assert file.exists()


def test_local_resume_validation_obeys_pause_before_touching_cache(tmp_path):
    from nassav.task_control_rules import TaskPauseRequested

    guard = HLSResumeGuard()
    file = tmp_path / "temp/DL-1/track/0.ts"
    file.parent.mkdir(parents=True)
    file.write_bytes(b"complete")
    manifest = {"safe": True, "identity": "same", "urls": ["unused"]}
    checkpoint = {"manifest": manifest, "segments": guard.snapshot(tmp_path, "DL-1")}
    file.write_bytes(b"damaged")

    def stop():
        raise TaskPauseRequested("pause")

    with pytest.raises(TaskPauseRequested):
        guard.prepare(tmp_path, "DL-1", manifest, checkpoint, {}, stop)
    assert file.read_bytes() == b"damaged"


def test_manifest_query_refresh_and_content_identity(context):
    playlist = b"#EXTM3U\n#EXTINF:2,\nsegment.ts?token=new\n#EXT-X-ENDLIST\n"
    guard = HLSResumeGuard(fetch=lambda *args: playlist)
    first = guard.describe("https://offline.invalid/index.m3u8?old", {}, lambda: None)
    second = guard.describe("https://offline.invalid/index.m3u8?new", {}, lambda: None)
    assert first["identity"] == second["identity"]


def test_unknown_writer_keeps_running_reservation_and_does_not_clean(context):
    from nassav.task_processes import TaskWritersAlive

    ctx = context

    def unknown(**kwargs):
        raise TaskWritersAlive("writer cannot be confirmed exited")

    ctx.downloader.action = unknown
    with pytest.raises(TaskWritersAlive):
        execute(ctx)
    assert ctx.lease.retained and not ctx.lease.closed
    assert ctx.records.get(ctx.job["job_id"])["state"] == "running"
    assert (ctx.assets.roots["video"] / ".tasks" / ctx.job["job_id"]).exists()


def test_unknown_cache_still_acknowledges_pause_but_blocks_resume(context):
    from nassav.task_control_rules import TaskConflict

    ctx = context
    ctx.downloader.action = lambda **kwargs: request(ctx, "pause")

    def unknown(*args):
        raise DownloadRestartRequired("unknown cache")

    ctx.guard.snapshot = unknown
    result = execute(ctx)
    assert result["status"] == "paused"
    assert result["snapshot"]["allowed_actions"] == ["cancel"]
    with pytest.raises(TaskConflict):
        request(ctx, "resume")
    assert not ctx.saved


def test_pause_releases_real_redis_slot_for_a_second_job(context, isolated_redis):
    from nassav.download_leases import DownloadLease

    ctx = context
    first = DownloadLease("DL-1", lambda: isolated_redis)
    ctx.runner.lease = first
    ctx.downloader.action = lambda **kwargs: request(ctx, "pause")
    assert execute(ctx)["status"] == "paused"
    assert not isolated_redis.exists(first.GLOBAL_KEY, first.task_key)
    second, _ = ctx.records.create(
        "download", "DL-2", owner_id=ctx.owner.pk, action="download"
    )
    ctx.runner.lease = DownloadLease("DL-2", lambda: isolated_redis)
    ctx.downloader.action = lambda **kwargs: None
    assert execute(ctx, second)["status"] == "succeeded"
    assert ctx.saved == ["DL-2"]
    assert ctx.records.get(ctx.job["job_id"])["state"] == "paused"


def test_unknown_writer_lease_is_retained_without_touching_a_successor(isolated_redis):
    from nassav.download_leases import DownloadLease

    lease = DownloadLease("UNKNOWN-1", lambda: isolated_redis)
    lease.start()
    assert lease.acquire_global()
    isolated_redis.set(lease.GLOBAL_KEY, "successor", ex=60)
    lease.retain_for_recovery()
    lease.close()
    assert isolated_redis.get(lease.task_key) == lease.owner.encode()
    assert isolated_redis.ttl(lease.task_key) == -1
    assert isolated_redis.get(lease.GLOBAL_KEY) == b"successor"
    assert isolated_redis.ttl(lease.GLOBAL_KEY) > 0


def test_projection_failure_does_not_undo_committed_download(context):
    ctx = context

    def offline(*args, **kwargs):
        raise RuntimeError("Channels unavailable")

    ctx.runner.project = offline
    assert execute(ctx)["status"] == "succeeded"
    assert ctx.saved == ["DL-1"]


def test_manifest_transport_aborts_callback_and_enforces_total_timeout(monkeypatch):
    from curl_cffi import CurlOpt
    from nassav.task_control_rules import TaskPauseRequested

    captured = {}
    checks = []

    def check():
        checks.append(True)
        if len(checks) == 2:
            raise TaskPauseRequested("stop during response")

    class Session:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def get(self, url, **kwargs):
            captured.update(kwargs)
            assert kwargs["content_callback"](b"chunk") == 0xFFFFFFFF
            raise RuntimeError("curl write aborted")

    monkeypatch.setattr("nassav.download_resume.requests.Session", Session)
    with pytest.raises(TaskPauseRequested):
        HLSResumeGuard()._fetch("https://offline.invalid/index.m3u8", {}, check)
    assert captured["timeout"] == (5, 55)
    assert captured["curl_options"][CurlOpt.PROXY] == ""


def test_validation_timeout_retains_workspace_and_allows_resume(context):
    from nassav.download_resume import DownloadValidationTimeout

    ctx = context

    def timeout(*args):
        raise DownloadValidationTimeout("temporary network timeout")

    ctx.guard.prepare = timeout
    result = ctx.runner.run(ctx.job["job_id"], ctx.job["task_id"])
    assert result["status"] == "paused"
    assert result["snapshot"]["error_code"] == "RESUME_VALIDATION_TIMEOUT"
    assert "resume" in result["snapshot"]["allowed_actions"]
    assert ctx.lease.closed and not ctx.lease.slot
    assert not ctx.saved
    resumed = request(ctx, "resume")
    assert resumed["generation"] == 2


def test_rejected_playback_is_refreshed_once_then_runs_resume_guard(context):
    from curl_cffi.requests.exceptions import HTTPError
    from unittest.mock import Mock

    ctx = context
    old = ctx.runner.resolver.resolve
    ctx.runner.resolver.resolve = Mock(side_effect=old)
    original = ctx.guard.describe
    ctx.guard.describe = Mock(
        side_effect=[
            HTTPError("expired", response=SimpleNamespace(status_code=403)),
            original(),
        ]
    )
    ctx.guard.prepare = Mock()
    assert execute(ctx)["status"] == "succeeded"
    assert ctx.runner.resolver.resolve.call_count == 2
    assert ctx.runner.resolver.resolve.call_args.kwargs["force"] is True
    assert ctx.guard.describe.call_count == 2
    ctx.guard.prepare.assert_called_once()


def test_rejected_refreshed_playback_is_not_retried_forever(context):
    from curl_cffi.requests.exceptions import HTTPError
    from unittest.mock import Mock

    ctx = context
    ctx.guard.describe = Mock(
        side_effect=HTTPError("expired", response=SimpleNamespace(status_code=403))
    )
    assert execute(ctx)["status"] == "failed"
    assert ctx.guard.describe.call_count == 2
    assert ctx.downloader.called == 0
