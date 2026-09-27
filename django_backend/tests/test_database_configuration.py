import os
import subprocess
import sys
from pathlib import Path

from nassav.management.commands.backup_database import Command


def test_postgresql_retention_preserves_sqlite_rollback_snapshots(tmp_path):
    sqlite_backup = tmp_path / "database_20260101_000000"
    postgres_backup = tmp_path / "database_postgresql_20260101_000000"
    sqlite_backup.mkdir()
    postgres_backup.mkdir()
    old_time = 1
    os.utime(sqlite_backup, (old_time, old_time))
    os.utime(postgres_backup, (old_time, old_time))

    deleted = Command().cleanup_old_backups(
        tmp_path, days=1, engine="django.db.backends.postgresql"
    )

    assert deleted == 1
    assert sqlite_backup.exists()
    assert not postgres_backup.exists()


def test_postgresql_configuration_requires_password():
    backend_root = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    environment.update(
        {
            "DJANGO_SETTINGS_MODULE": "django_project.settings",
            "DB_ENGINE": "postgres",
            "DB_NAME": "nassav",
            "DB_USER": "nassav",
            "DB_HOST": "localhost",
        }
    )
    environment.pop("DB_PASSWORD", None)
    environment.pop("DB_PASSWORD_FILE", None)

    result = subprocess.run(
        [sys.executable, "-c", "from django.conf import settings; settings.DATABASES"],
        cwd=backend_root,
        env=environment,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "DB_PASSWORD or DB_PASSWORD_FILE" in result.stderr
