"""Runtime ownership repair must preserve media, lock identity and task checkpoints."""

import importlib.util
import os
from pathlib import Path

import pytest


@pytest.fixture
def permissions():
    path = (
        Path(__file__).resolve().parents[2] / "scripts/prepare_backend_permissions.py"
    )
    spec = importlib.util.spec_from_file_location("backend_permissions_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_check_is_read_only_and_repair_requires_stopped_writers(permissions, tmp_path):
    data, resource = tmp_path / "data", tmp_path / "media"
    result = permissions.prepare(data, resource, os.getuid(), os.getgid())
    assert result["status"] == "needs_repair"
    assert not data.exists() and not resource.exists()
    with pytest.raises(ValueError, match="writers-stopped"):
        permissions.prepare(data, resource, os.getuid(), os.getgid(), repair=True)
    assert not data.exists()


def test_repair_preserves_lock_inode_cache_and_published_files(permissions, tmp_path):
    data, resource = tmp_path / "data", tmp_path / "media"
    lock = resource / ".nassav-task-locks/job.lock"
    cached = resource / "video/.tasks/job/download/temp/0.ts"
    published = resource / "video/video.mp4"
    for file in (lock, cached, published):
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(b"retained")
        file.chmod(0o400)
    inode = lock.stat().st_ino
    permissions.prepare(
        data, resource, os.getuid(), os.getgid(), repair=True, writers_stopped=True
    )
    assert lock.stat().st_ino == inode
    assert (
        lock.read_bytes()
        == cached.read_bytes()
        == published.read_bytes()
        == b"retained"
    )
    assert cached.stat().st_mode & 0o600 == 0o600
    assert published.stat().st_mode & 0o777 == 0o400
    assert (
        permissions.prepare(data, resource, os.getuid(), os.getgid())["status"] == "ok"
    )


@pytest.mark.parametrize("link", ["symlink", "hardlink"])
def test_unsafe_entry_rejected_before_any_mutation(permissions, tmp_path, link):
    data, resource = tmp_path / "data", tmp_path / "media"
    directory = resource / "video/.tasks/job"
    directory.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.write_bytes(b"keep")
    outside.chmod(0o400)
    if link == "symlink":
        (directory / "link").symlink_to(outside)
    else:
        os.link(outside, directory / "link")
    with pytest.raises(ValueError, match="Refusing"):
        permissions.prepare(
            data, resource, os.getuid(), os.getgid(), repair=True, writers_stopped=True
        )
    assert not data.exists()
    assert outside.stat().st_mode & 0o777 == 0o400


def test_resource_symlink_requires_explicit_real_path(permissions, tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    linked = tmp_path / "linked"
    linked.symlink_to(real, target_is_directory=True)
    with pytest.raises(ValueError, match="verified real path"):
        permissions.prepare(tmp_path / "data", linked, os.getuid(), os.getgid())


def test_repair_does_not_accept_root_identity(permissions, tmp_path):
    with pytest.raises(ValueError, match="non-root"):
        permissions.prepare(tmp_path / "data", tmp_path / "media", 0, 0)


def test_parent_traversal_cannot_bypass_root_guard(permissions, tmp_path):
    with pytest.raises(ValueError, match="parent traversal"):
        permissions.prepare(
            tmp_path / "..", tmp_path / "media", os.getuid(), os.getgid()
        )
