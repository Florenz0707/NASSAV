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


def test_postgresql_configuration_requires_password(tmp_path):
    backend_root = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    environment.update(
        {
            "DJANGO_SETTINGS_MODULE": "django_project.settings",
            "DB_ENGINE": "postgres",
            "NASSAV_COMPOSE_DB_MODE": "postgres",
            "DB_NAME": "nassav",
            "DB_USER": "nassav",
            "DB_HOST": "localhost",
        }
    )
    marker = tmp_path / ".nassav-db-mode"
    marker.write_text("postgres\n")
    environment["NASSAV_DB_MODE_FILE"] = str(marker)
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
    template_path = backend_root / "config" / "config.example.yaml"
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
    environment.pop("NASSAV_COMPOSE_DB_MODE", None)
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


def test_compose_sqlite_mode_rejects_postgres_override(tmp_path):
    backend_root = Path(__file__).resolve().parents[1]
    database = tmp_path / "unexpected.sqlite3"
    environment = os.environ.copy()
    environment.update(
        {
            "DJANGO_SETTINGS_MODULE": "django_project.settings",
            "NASSAV_CONFIG_PATH": str(backend_root / "config" / "config.example.yaml"),
            "NASSAV_COMPOSE_DB_MODE": "sqlite",
            "DB_ENGINE": "postgres",
            "DATABASE_PATH": str(database),
        }
    )
    result = subprocess.run(
        [sys.executable, "-c", "from django.conf import settings; settings.DATABASES"],
        cwd=backend_root,
        env=environment,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "Compose database mode conflicts with DB_ENGINE" in result.stderr
    assert not database.exists()


def test_postgres_connection_failure_never_opens_sqlite(tmp_path):
    backend_root = Path(__file__).resolve().parents[1]
    database = tmp_path / "unexpected.sqlite3"
    environment = os.environ.copy()
    environment.update(
        {
            "DJANGO_SETTINGS_MODULE": "django_project.settings",
            "NASSAV_CONFIG_PATH": str(backend_root / "config" / "config.example.yaml"),
            "NASSAV_COMPOSE_DB_MODE": "postgres",
            "DB_ENGINE": "postgres",
            "DB_NAME": "nassav_p2_disposable",
            "DB_USER": "nassav_p2_disposable",
            "DB_HOST": "127.0.0.1",
            "DB_PORT": "1",
            "DB_PASSWORD": "dummy-test-password",
            "PGCONNECT_TIMEOUT": "2",
            "DATABASE_PATH": str(database),
        }
    )
    marker = tmp_path / ".nassav-db-mode"
    marker.write_text("postgres\n")
    environment["NASSAV_DB_MODE_FILE"] = str(marker)
    environment.pop("DB_PASSWORD_FILE", None)
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from django.db import connections; print(connections['default'].vendor); "
            "connections['default'].ensure_connection()",
        ],
        cwd=backend_root,
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode != 0
    # Network environments may refuse, time out, or accept then close the port.
    # The contract is PostgreSQL failure without creating a SQLite fallback.
    assert "django.db.utils.OperationalError:" in result.stderr
    assert result.stdout.strip() == "postgresql"
    assert not database.exists()


def test_compose_mode_marker_blocks_base_files_before_sqlite_connection(tmp_path):
    backend_root = Path(__file__).resolve().parents[1]
    database = tmp_path / "unexpected.sqlite3"
    marker = tmp_path / ".nassav-db-mode"
    marker.write_text("postgres\n")
    environment = os.environ.copy()
    environment.update(
        {
            "DJANGO_SETTINGS_MODULE": "django_project.settings",
            "NASSAV_CONFIG_PATH": str(backend_root / "config" / "config.example.yaml"),
            "NASSAV_COMPOSE_DB_MODE": "sqlite",
            "NASSAV_DB_MODE_FILE": str(marker),
            "DB_ENGINE": "sqlite",
            "DATABASE_PATH": str(database),
        }
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from django.db import connections; connections['default'].ensure_connection()",
        ],
        cwd=backend_root,
        env=environment,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "Data directory database mode conflicts with Compose mode" in result.stderr
    assert not database.exists()


def test_compose_mode_requires_declaration_before_sqlite_connection(tmp_path):
    backend_root = Path(__file__).resolve().parents[1]
    database = tmp_path / "unexpected.sqlite3"
    environment = os.environ.copy()
    environment.update(
        {
            "DJANGO_SETTINGS_MODULE": "django_project.settings",
            "NASSAV_CONFIG_PATH": str(backend_root / "config" / "config.example.yaml"),
            "NASSAV_COMPOSE_DB_MODE": "sqlite",
            "NASSAV_DB_MODE_FILE": str(tmp_path / "missing"),
            "DB_ENGINE": "sqlite",
            "DATABASE_PATH": str(database),
        }
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from django.db import connections; connections['default'].ensure_connection()",
        ],
        cwd=backend_root,
        env=environment,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "Database mode declaration is missing or unreadable" in result.stderr
    assert not database.exists()
