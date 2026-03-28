import os
from datetime import datetime, timedelta
from pathlib import Path

from nassav.management.commands.cleanup_logs import Command


def _touch_with_mtime(path: Path, content: str, mtime: datetime) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    timestamp = mtime.timestamp()
    os.utime(path, (timestamp, timestamp))


def test_cleanup_old_logs_removes_expired_files_and_empty_dirs(tmp_path):
    command = Command()
    cutoff_time = datetime.now() - timedelta(days=30)

    old_dir = tmp_path / "archive"
    old_file = old_dir / "2026-01-01.log"
    keep_file = tmp_path / "2026-03-28.log"

    _touch_with_mtime(old_file, "old", cutoff_time - timedelta(days=10))
    _touch_with_mtime(keep_file, "keep", cutoff_time + timedelta(days=1))

    deleted = command.cleanup_old_logs(tmp_path, cutoff_time)

    assert deleted == 1
    assert not old_file.exists()
    assert not old_dir.exists()
    assert keep_file.exists()


def test_cleanup_old_logs_keeps_recent_uvicorn_files(tmp_path):
    command = Command()
    cutoff_time = datetime.now() - timedelta(days=30)

    uvicorn_log = tmp_path / "uvicorn.log.2026-03-15"
    access_log = tmp_path / "uvicorn_access.log"

    _touch_with_mtime(uvicorn_log, "recent rotated", cutoff_time + timedelta(days=2))
    _touch_with_mtime(access_log, "current", cutoff_time + timedelta(hours=1))

    deleted = command.cleanup_old_logs(tmp_path, cutoff_time)

    assert deleted == 0
    assert uvicorn_log.exists()
    assert access_log.exists()
