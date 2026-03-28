import os
from datetime import datetime, timedelta
from pathlib import Path

from nassav.management.commands.sync_backups import Command


def _touch_with_mtime(path: Path, content: str, mtime: datetime) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    timestamp = mtime.timestamp()
    os.utime(path, (timestamp, timestamp))


def test_cleanup_expired_target_files_removes_old_files_and_empty_dirs(tmp_path):
    command = Command()
    cutoff_time = datetime.now() - timedelta(days=30)

    old_dir = tmp_path / "backup" / "database_20260101_010000"
    old_file = old_dir / "db.sqlite3"
    new_file = tmp_path / "backup" / "database_20260328_010000" / "db.sqlite3"

    _touch_with_mtime(old_file, "old", cutoff_time - timedelta(days=10))
    _touch_with_mtime(new_file, "new", cutoff_time + timedelta(days=1))

    deleted = command._cleanup_expired_target_files(tmp_path / "backup", cutoff_time)

    assert deleted == 1
    assert not old_file.exists()
    assert not old_dir.exists()
    assert new_file.exists()


def test_cleanup_expired_target_files_keeps_excluded_files(tmp_path):
    command = Command()
    cutoff_time = datetime.now() - timedelta(days=30)

    excluded = tmp_path / "celery_beat" / "celerybeat-schedule.db"
    report = tmp_path / "celery_beat" / "resources_consistency_report.json"

    _touch_with_mtime(excluded, "state", cutoff_time - timedelta(days=10))
    _touch_with_mtime(report, "{}", cutoff_time - timedelta(days=10))

    deleted = command._cleanup_expired_target_files(
        tmp_path / "celery_beat",
        cutoff_time,
        exclude_files=["celerybeat-schedule.db"],
    )

    assert deleted == 1
    assert excluded.exists()
    assert not report.exists()
