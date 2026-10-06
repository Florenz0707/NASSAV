"""Real filesystem/DB tests for private staging and recoverable publication."""

from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model

from nassav.task_assets import (
    AssetPromotion,
    TaskAssetError,
    TaskAssetRecoveryRequired,
    TaskAssets,
)
from nassav.task_control_rules import (
    TaskConflict,
    TaskExecutionInvalid,
    TaskPauseRequested,
)
from nassav.task_models import TaskArtifact, TaskAssetTarget
from nassav.task_records import DjangoTaskRecords


@pytest.fixture
def context(db, tmp_path):
    records = DjangoTaskRecords()
    user = get_user_model().objects.create_user(username="assets-owner")
    assets = TaskAssets(
        {kind: tmp_path / kind for kind in ("cover", "avatar", "video")}, records
    )
    job, _ = records.create("scrape", "ASSET-1", owner_id=user.pk, action="refresh")
    token = records.claim(job["job_id"], job["task_id"])
    return assets, records, user, job, token


def produce(data):
    def write(path):
        path.write_bytes(data)
        return True

    return write


def command(context, action):
    _, records, user, job, _ = context
    current = records.get(job["job_id"])
    return records.request(
        job["job_id"],
        action,
        expected_version=current["version"],
        request_id=str(uuid4()),
        actor_id=user.pk,
    )


def test_cancel_cleans_private_files_and_keeps_existing_shared_files(context):
    assets, records, _, job, token = context
    video = assets.roots["video"] / "ASSET-1.mp4"
    video.parent.mkdir()
    video.write_bytes(b"existing complete video")
    assets.stage(token, "cover", "cover.jpg", "cover", produce(b"new cover"))
    assets.stage(token, "avatar", "actor.jpg", "avatar", produce(b"new avatar"))
    work = assets.workspace(token, "video")
    (work / "partial.ts").write_bytes(b"partial")
    command(context, "cancel")
    with pytest.raises(TaskExecutionInvalid):
        assets.cleanup(job["job_id"])
    records.acknowledge_stop(token)
    assert assets.cleanup(job["job_id"])["cleanup_state"] == "completed"
    assert video.read_bytes() == b"existing complete video"
    assert all(
        not (root / ".tasks" / job["job_id"]).exists() for root in assets.roots.values()
    )
    assert assets.cleanup(job["job_id"])["cleanup_state"] == "completed"


def test_committed_resource_and_reused_avatar_survive_cancel(context):
    assets, records, _, job, token = context
    avatar = assets.roots["avatar"] / "actor.jpg"
    avatar.parent.mkdir()
    avatar.write_bytes(b"shared")
    cover_id = assets.stage(token, "cover", "cover.jpg", "cover", produce(b"cover"))
    avatar_id = assets.stage(token, "avatar", "actor.jpg", "avatar", produce(b"fresh"))
    assets.commit(
        token,
        [
            AssetPromotion(cover_id, "ASSET-1.jpg"),
            AssetPromotion(avatar_id, "actor.jpg", True),
        ],
        lambda: None,
        resource_saved=True,
    )
    command(context, "cancel")
    records.acknowledge_stop(token)
    assets.cleanup(job["job_id"])
    assert avatar.read_bytes() == b"shared"
    assert (assets.roots["cover"] / "ASSET-1.jpg").read_bytes() == b"cover"
    assert records.get(job["job_id"])["resource_saved"]


@pytest.mark.parametrize(
    "old,new", [(b"old", b"new"), (b"same", b"same"), (b"", b"new")]
)
def test_metadata_failure_restores_files_and_leaves_retryable_private_asset(
    context, old, new
):
    assets, _, _, _, token = context
    target = assets.roots["cover"] / "ASSET-1.jpg"
    target.parent.mkdir()
    if old:
        target.write_bytes(old)
    asset_id = assets.stage(token, "cover", "cover.jpg", "cover", produce(new))

    def fail():
        raise RuntimeError("database callback failed")

    with pytest.raises(RuntimeError, match="database callback"):
        assets.commit(token, [AssetPromotion(asset_id, "ASSET-1.jpg")], fail)
    assert target.read_bytes() == old if old else not target.exists()
    asset = TaskArtifact.objects.get(pk=asset_id)
    assert asset.state == "staged"
    assert (
        assets.roots["cover"] / ".tasks" / token.job_id / "cover.jpg"
    ).read_bytes() == new
    assets.commit(token, [AssetPromotion(asset_id, "ASSET-1.jpg")], lambda: None)
    assert target.read_bytes() == new


def test_pause_between_journal_and_publish_does_not_move_identical_existing_file(
    context, monkeypatch
):
    assets, records, _, _, token = context
    target = assets.roots["cover"] / "ASSET-1.jpg"
    target.parent.mkdir()
    target.write_bytes(b"same")
    asset_id = assets.stage(token, "cover", "cover.jpg", "cover", produce(b"same"))
    original = records.controlled_transaction

    def pause_after_prepare(*args, **kwargs):
        result = original(*args, **kwargs)
        if kwargs.get("checkpoint", {}).get("preparing_commit"):
            command(context, "pause")
        return result

    monkeypatch.setattr(records, "controlled_transaction", pause_after_prepare)
    with pytest.raises(TaskPauseRequested):
        assets.commit(
            token,
            [AssetPromotion(asset_id, "ASSET-1.jpg")],
            lambda: pytest.fail("metadata saved"),
        )
    assert target.read_bytes() == b"same"
    assert TaskArtifact.objects.get(pk=asset_id).state == "staged"


@pytest.mark.parametrize(
    "relative", ["../escape", "/escape", "a//b", "a/../b", ".", "a\\b", "a/./b"]
)
def test_path_traversal_rejected(context, relative):
    assets, _, _, _, token = context
    with pytest.raises(ValueError):
        assets.stage(token, "cover", relative, "cover", produce(b"bad"))


def test_symlink_parent_and_produced_symlink_rejected(context, tmp_path):
    assets, _, _, _, token = context
    outside = tmp_path / "outside"
    outside.mkdir()
    outside_file = outside / "file"
    outside_file.write_bytes(b"untouched")
    workspace = assets.workspace(token, "cover", "safe")
    (workspace / "linked").symlink_to(outside, target_is_directory=True)
    with pytest.raises(TaskAssetError, match="符号链接"):
        assets.stage(token, "cover", "safe/linked/file", "cover", produce(b"bad"))

    def link(path):
        path.symlink_to(outside_file)
        return True

    with pytest.raises(TaskAssetError, match="符号链接"):
        assets.stage(token, "cover", "link", "cover", link)
    assert outside_file.read_bytes() == b"untouched"


def test_late_producer_cannot_record_after_owner_is_invalidated(context):
    assets, records, _, _, token = context

    def late(path):
        path.write_bytes(b"late")
        command(context, "pause")
        records.acknowledge_stop(token)
        command(context, "resume")
        return True

    with pytest.raises(TaskExecutionInvalid):
        assets.stage(token, "cover", "late.jpg", "cover", late)
    asset = TaskArtifact.objects.get(job_id=token.job_id)
    assert not asset.sha256


def test_cleanup_permission_failure_is_retryable(context, monkeypatch):
    assets, records, _, job, token = context
    assets.stage(token, "cover", "cover.jpg", "cover", produce(b"cover"))
    command(context, "cancel")
    records.acknowledge_stop(token)
    import shutil

    original = shutil.rmtree

    def fail(*args, **kwargs):
        raise PermissionError("cannot delete")

    fail.avoids_symlink_attacks = True
    monkeypatch.setattr(shutil, "rmtree", fail)
    failed = assets.cleanup(job["job_id"])
    assert failed["state"] == "cancelled"
    assert failed["cleanup_state"] == "failed"
    assert failed["allowed_actions"] == ["cleanup_retry"]
    assert command(context, "cleanup_retry")["cleanup_state"] == "pending"
    monkeypatch.setattr(shutil, "rmtree", original)
    assert assets.cleanup(job["job_id"])["cleanup_state"] == "completed"


def test_crash_recovery_refuses_later_target_epoch(context, monkeypatch):
    assets, records, _, job, token = context
    target = assets.roots["cover"] / "ASSET-1.jpg"
    asset_id = assets.stage(token, "cover", "cover.jpg", "cover", produce(b"new"))
    original = assets._rollback

    def crashed(artifacts):
        raise TaskAssetRecoveryRequired("simulated worker crash")

    monkeypatch.setattr(assets, "_rollback", crashed)

    def fail():
        raise RuntimeError("DB failed")

    with pytest.raises(TaskAssetRecoveryRequired):
        assets.commit(token, [AssetPromotion(asset_id, "ASSET-1.jpg")], fail)
    command(context, "pause")
    records.acknowledge_stop(token)
    with pytest.raises(TaskConflict, match="恢复"):
        command(context, "resume")
    # Another publisher writes identical bytes but has a distinct ownership epoch.
    TaskAssetTarget.objects.filter(root="cover", relative_path="ASSET-1.jpg").update(
        marker=uuid4()
    )
    monkeypatch.setattr(assets, "_rollback", original)
    with pytest.raises(TaskAssetRecoveryRequired, match="后续任务"):
        assets.recover(job["job_id"])
    assert target.read_bytes() == b"new"


def test_stopped_job_can_recover_interrupted_publish(context, monkeypatch):
    assets, records, _, job, token = context
    target = assets.roots["cover"] / "ASSET-1.jpg"
    target.parent.mkdir()
    target.write_bytes(b"old")
    asset_id = assets.stage(token, "cover", "cover.jpg", "cover", produce(b"new"))
    original = assets._rollback

    def crash(artifacts):
        raise TaskAssetRecoveryRequired("crash")

    monkeypatch.setattr(assets, "_rollback", crash)
    with pytest.raises(TaskAssetRecoveryRequired):
        assets.commit(
            token,
            [AssetPromotion(asset_id, "ASSET-1.jpg")],
            lambda: (_ for _ in ()).throw(RuntimeError("fail")),
        )
    assert target.read_bytes() == b"new"
    with pytest.raises(TaskExecutionInvalid):
        assets.recover(job["job_id"])
    command(context, "cancel")
    records.acknowledge_stop(token)
    monkeypatch.setattr(assets, "_rollback", original)
    assert assets.cleanup(job["job_id"])["cleanup_state"] == "completed"
    assert target.read_bytes() == b"old"


def test_missing_rollback_backup_preserves_formal_file_for_manual_recovery(
    context, monkeypatch
):
    assets, records, _, job, token = context
    target = assets.roots["cover"] / "ASSET-1.jpg"
    target.parent.mkdir()
    target.write_bytes(b"old")
    asset_id = assets.stage(token, "cover", "cover.jpg", "cover", produce(b"new"))
    original = assets._rollback

    def crash(artifacts):
        raise TaskAssetRecoveryRequired("crash")

    monkeypatch.setattr(assets, "_rollback", crash)
    with pytest.raises(TaskAssetRecoveryRequired):
        assets.commit(
            token,
            [AssetPromotion(asset_id, "ASSET-1.jpg")],
            lambda: (_ for _ in ()).throw(RuntimeError("fail")),
        )
    asset = TaskArtifact.objects.get(pk=asset_id)
    (
        assets.roots["cover"] / ".tasks" / job["job_id"] / asset.details["backup"]
    ).unlink()
    command(context, "cancel")
    records.acknowledge_stop(token)
    monkeypatch.setattr(assets, "_rollback", original)
    assert assets.cleanup(job["job_id"])["cleanup_state"] == "failed"
    assert target.read_bytes() == b"new"


def test_metadata_changes_and_multi_file_publication_roll_back_together(context):
    from nassav.models import AVResource

    assets, _, _, _, token = context
    ids = [
        assets.stage(token, root, "file", root, produce(root.encode()))
        for root in ["cover", "avatar"]
    ]

    def fail():
        AVResource.objects.create(avid="ASSET-1")
        raise RuntimeError("second operation failed")

    with pytest.raises(RuntimeError):
        assets.commit(
            token,
            [
                AssetPromotion(ids[0], "ASSET-1.jpg"),
                AssetPromotion(ids[1], "actor.jpg"),
            ],
            fail,
        )
    assert not AVResource.objects.filter(avid="ASSET-1").exists()
    assert not (assets.roots["cover"] / "ASSET-1.jpg").exists()
    assert not (assets.roots["avatar"] / "actor.jpg").exists()


def test_cleanup_symlink_root_keeps_external_directory(context, tmp_path):
    assets, records, _, job, token = context
    assets.stage(token, "cover", "file", "cover", produce(b"private"))
    outside = tmp_path / "external"
    outside.mkdir()
    (outside / "keep").write_bytes(b"keep")
    (assets.roots["video"] / ".tasks").mkdir(parents=True)
    (assets.roots["video"] / ".tasks" / job["job_id"]).symlink_to(
        outside, target_is_directory=True
    )
    command(context, "cancel")
    records.acknowledge_stop(token)
    assert assets.cleanup(job["job_id"])["cleanup_state"] == "failed"
    assert (outside / "keep").read_bytes() == b"keep"


def test_successful_job_cleanup_removes_private_backup_keeps_new_cover(context):
    assets, records, _, job, token = context
    target = assets.roots["cover"] / "ASSET-1.jpg"
    target.parent.mkdir()
    target.write_bytes(b"old")
    asset_id = assets.stage(token, "cover", "cover.jpg", "cover", produce(b"new"))
    assets.commit(token, [AssetPromotion(asset_id, "ASSET-1.jpg")], lambda: None)
    assert records.finish(token, "succeeded")["cleanup_state"] == "pending"
    assert assets.cleanup(job["job_id"])["cleanup_state"] == "completed"
    assert target.read_bytes() == b"new"


@pytest.mark.parametrize("endpoint", ["resource", "downloads"])
def test_delete_endpoint_refuses_paused_job(context, api_client, settings, endpoint):
    assets, records, _, _, token = context
    settings.COVER_DIR = assets.roots["cover"]
    settings.VIDEO_DIR = assets.roots["video"]
    command(context, "pause")
    records.acknowledge_stop(token)
    response = api_client.delete(f"/nassav/api/{endpoint}/ASSET-1")
    assert response.status_code == 409


def test_backup_ignores_task_workspace(tmp_path):
    from nassav.management.commands.sync_backups import Command

    source = tmp_path / "source"
    private = source / ".tasks" / "job" / "partial.mp4"
    private.parent.mkdir(parents=True)
    private.write_bytes(b"private")
    (source / "formal.mp4").write_bytes(b"formal")
    target = tmp_path / "target"
    assert Command()._sync_directory(source, target, None) == (1, 6)
    assert not (target / ".tasks").exists()
