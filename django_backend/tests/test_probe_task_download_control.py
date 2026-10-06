"""The local capability probe must refuse unsafe inputs before starting tools."""

import hashlib
import sys

import pytest

from scripts import probe_task_download_control as probe


def test_unknown_binary_does_not_create_workspace(tmp_path, monkeypatch):
    binary = tmp_path / "unknown-downloader"
    binary.write_bytes(b"unknown build")
    workspace = tmp_path / "workspace"
    monkeypatch.setattr(
        sys, "argv", ["probe", "--binary", str(binary), "--workspace", str(workspace)]
    )
    with pytest.raises(SystemExit) as error:
        probe.main()
    assert error.value.code == 2
    assert not workspace.exists()


def test_existing_workspace_is_not_modified(tmp_path, monkeypatch):
    binary = tmp_path / "fixture-binary"
    binary.write_bytes(b"test-only binary")
    monkeypatch.setattr(
        probe, "EXPECTED_BINARY_SHA256", hashlib.sha256(binary.read_bytes()).hexdigest()
    )
    workspace = tmp_path / "existing"
    workspace.mkdir()
    protected = workspace / "keep.mp4"
    protected.write_bytes(b"existing video")
    monkeypatch.setattr(
        sys, "argv", ["probe", "--binary", str(binary), "--workspace", str(workspace)]
    )
    with pytest.raises(SystemExit) as error:
        probe.main()
    assert error.value.code == 2
    assert protected.read_bytes() == b"existing video"
    assert list(workspace.iterdir()) == [protected]
