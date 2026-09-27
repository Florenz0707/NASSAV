"""Restore a custom-format PostgreSQL backup into an empty database."""

import os
import subprocess
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection


class Command(BaseCommand):
    help = "Restore a PostgreSQL custom-format backup into an empty PostgreSQL database"

    def add_arguments(self, parser):
        parser.add_argument("backup", type=Path, help="Path to database.dump")

    def handle(self, *args, **options):
        database = settings.DATABASES["default"]
        if database["ENGINE"] != "django.db.backends.postgresql":
            raise CommandError(
                "DB_ENGINE must be postgres to restore a PostgreSQL backup"
            )

        backup_path = options["backup"].resolve()
        if not backup_path.is_file() or backup_path.stat().st_size == 0:
            raise CommandError(f"Backup file is missing or empty: {backup_path}")
        try:
            subprocess.run(
                ["pg_restore", "--list", str(backup_path)],
                check=True,
                capture_output=True,
                text=True,
            )
            connection.ensure_connection()
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema NOT IN ('pg_catalog', 'information_schema'))"
                )
                has_tables = cursor.fetchone()[0]
            if has_tables:
                raise CommandError(
                    "Restore requires a fresh, empty database; no tables were changed"
                )

            environment = os.environ.copy()
            environment["PGPASSWORD"] = database["PASSWORD"]
            subprocess.run(
                [
                    "pg_restore",
                    "--exit-on-error",
                    "--no-owner",
                    "--no-acl",
                    "--host",
                    database["HOST"],
                    "--port",
                    str(database["PORT"]),
                    "--username",
                    database["USER"],
                    "--dbname",
                    database["NAME"],
                    str(backup_path),
                ],
                check=True,
                env=environment,
                capture_output=True,
                text=True,
            )
        except CommandError:
            raise
        except (OSError, subprocess.CalledProcessError) as exc:
            detail = getattr(exc, "stderr", None)
            raise CommandError(f"PostgreSQL restore failed: {detail or exc}") from exc

        self.stdout.write(f"Restored PostgreSQL backup: {backup_path}")
