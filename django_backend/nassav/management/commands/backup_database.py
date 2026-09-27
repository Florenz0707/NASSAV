"""Create a database backup for the configured Django database engine."""

import os
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection


class Command(BaseCommand):
    help = "Back up the configured SQLite or PostgreSQL database"

    def add_arguments(self, parser):
        parser.add_argument(
            "--days", type=int, default=30, help="Backup retention in days"
        )

    def handle(self, *args, **options):
        days = options["days"]
        engine = settings.DATABASES["default"]["ENGINE"]
        backup_base_dir = Path(settings.BASE_DIR) / "backup"
        backup_base_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        if engine == "django.db.backends.sqlite3":
            backup_dir = backup_base_dir / f"database_{timestamp}"
            self._backup_sqlite(backup_dir)
        elif engine == "django.db.backends.postgresql":
            backup_dir = backup_base_dir / f"database_postgresql_{timestamp}"
            self._backup_postgresql(backup_dir)
        else:
            raise CommandError(f"Unsupported database engine: {engine}")

        deleted_count = self.cleanup_old_backups(backup_base_dir, days, engine)
        self.stdout.write(f"Database backup complete: {backup_dir}")
        if deleted_count:
            self.stdout.write(f"Removed {deleted_count} expired backup(s).")

    def _backup_sqlite(self, backup_dir: Path) -> None:
        db_path = Path(settings.DATABASES["default"]["NAME"])
        if not db_path.is_file():
            raise CommandError(f"SQLite database file does not exist: {db_path}")

        backup_dir.mkdir(parents=True)
        try:
            self.stdout.write("Checkpointing SQLite WAL...")
            with connection.cursor() as cursor:
                cursor.execute("PRAGMA wal_checkpoint(FULL)")
                checkpoint_result = cursor.fetchall()

            shutil.copy2(db_path, backup_dir / "db.sqlite3")
            copied_files = []
            for suffix in ("-wal", "-shm"):
                source = Path(f"{db_path}{suffix}")
                if source.exists():
                    shutil.copy2(source, backup_dir / f"db.sqlite3{suffix}")
                    copied_files.append(source.name)
            self._write_metadata(
                backup_dir,
                "sqlite",
                f"Database path: {db_path}\nWAL checkpoint: {checkpoint_result}\n"
                f"WAL/SHM files copied: {', '.join(copied_files) or 'none'}\n",
            )
        except Exception:
            shutil.rmtree(backup_dir, ignore_errors=True)
            raise

    def _backup_postgresql(self, backup_dir: Path) -> None:
        database = settings.DATABASES["default"]
        backup_dir.mkdir(parents=True)
        dump_path = backup_dir / "database.dump"
        try:
            connection.ensure_connection()
            with connection.cursor() as cursor:
                cursor.execute("SHOW server_version_num")
                server_version = int(cursor.fetchone()[0])
            dump_version = subprocess.run(
                ["pg_dump", "--version"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            client_major = int(dump_version.split()[2].split(".")[0])
            server_major = server_version // 10000
            if client_major != server_major:
                raise CommandError(
                    f"pg_dump major version {client_major} does not match server major version {server_major}"
                )

            command = [
                "pg_dump",
                "--format=custom",
                "--no-owner",
                "--no-acl",
                "--file",
                str(dump_path),
                "--host",
                database["HOST"],
                "--port",
                str(database["PORT"]),
                "--username",
                database["USER"],
                database["NAME"],
            ]
            environment = os.environ.copy()
            environment["PGPASSWORD"] = database["PASSWORD"]
            subprocess.run(
                command, check=True, env=environment, capture_output=True, text=True
            )
            if not dump_path.is_file() or dump_path.stat().st_size == 0:
                raise CommandError("pg_dump did not produce a non-empty backup")
            subprocess.run(
                ["pg_restore", "--list", str(dump_path)],
                check=True,
                capture_output=True,
                text=True,
            )
            self._write_metadata(
                backup_dir,
                "postgresql",
                f"Server major version: {server_major}\nDump client: {dump_version}\n",
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            shutil.rmtree(backup_dir, ignore_errors=True)
            detail = getattr(exc, "stderr", None)
            raise CommandError(f"PostgreSQL backup failed: {detail or exc}") from exc
        except Exception:
            shutil.rmtree(backup_dir, ignore_errors=True)
            raise

    @staticmethod
    def _write_metadata(backup_dir: Path, engine: str, details: str) -> None:
        (backup_dir / "backup_info.txt").write_text(
            f"Database engine: {engine}\nBackup time: {datetime.now().isoformat()}\n{details}",
            encoding="utf-8",
        )

    def cleanup_old_backups(self, backup_dir: Path, days: int, engine: str) -> int:
        cutoff_time = time.time() - days * 86400
        deleted_count = 0
        for item in backup_dir.iterdir():
            if not item.is_dir() or item.stat().st_mtime >= cutoff_time:
                continue
            if engine == "django.db.backends.postgresql":
                # Keep every SQLite snapshot available throughout the rollback window.
                if not item.name.startswith("database_postgresql_"):
                    continue
            elif not item.name.startswith("database_") or item.name.startswith(
                "database_postgresql_"
            ):
                continue
            shutil.rmtree(item)
            deleted_count += 1
        return deleted_count
