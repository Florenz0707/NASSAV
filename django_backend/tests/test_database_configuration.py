import os
import subprocess
import sys
from pathlib import Path

import yaml

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
    assert "DB_PASSWORD, DB_PASSWORD_FILE, or Database.Password" in result.stderr


def test_postgresql_settings_load_from_yaml(tmp_path):
    backend_root = Path(__file__).resolve().parents[1]
    config_path = tmp_path / "config.yaml"
    template_path = backend_root / "config" / "template-config.yaml"
    config = yaml.safe_load(template_path.read_text(encoding="utf-8"))
    config["Database"].update(
        {
            "Engine": "postgres",
            "Host": "127.0.0.1",
            "Port": 5433,
            "Schema": "dev_schema",
            "Name": "dev_database",
            "User": "dev_user",
            "Password": "local-development-password",
        }
    )
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    environment = os.environ.copy()
    environment["DJANGO_SETTINGS_MODULE"] = "django_project.settings"
    environment["NASSAV_CONFIG_PATH"] = str(config_path)
    for name in (
        "DB_ENGINE",
        "DB_HOST",
        "DB_PORT",
        "DB_NAME",
        "DB_USER",
        "DB_PASSWORD",
        "DB_PASSWORD_FILE",
        "DB_CONN_MAX_AGE",
    ):
        environment.pop(name, None)

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from django.conf import settings; db = settings.DATABASES['default']; "
            "print('|'.join((db['ENGINE'], db['HOST'], db['PORT'], db['NAME'], "
            "db['USER'], db['OPTIONS']['options'])))",
        ],
        cwd=backend_root,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )

    assert result.stdout.strip() == (
        "django.db.backends.postgresql|127.0.0.1|5433|dev_database|dev_user|"
        "-c search_path=dev_schema"
    )
