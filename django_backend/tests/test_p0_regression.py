"""Isolated P0 samples for destructive and realtime behavior.

Run with DB_ENGINE=sqlite and a disposable config path, as described in
``tests/README.md``. These cases never use a live resource directory or Redis.
"""

import asyncio
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator

from django_project.asgi import application
from nassav import tasks
from nassav.models import AVResource


@pytest.mark.django_db
def test_resource_delete_removes_only_isolated_files(
    api_client, resource_factory, settings, tmp_path
):
    avid = "P0-DELETE-1"
    resource_factory(avid=avid)
    settings.COVER_DIR = tmp_path / "cover"
    settings.VIDEO_DIR = tmp_path / "video"
    settings.THUMBNAIL_DIR = tmp_path / "thumbnails"
    settings.RESOURCE_BACKUP_DIR = tmp_path / "resource_backup"
    cover = settings.COVER_DIR / f"{avid}.jpg"
    video = settings.VIDEO_DIR / f"{avid}.mp4"
    for path in (cover, video):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"p0-test-only")

    response = api_client.delete(f"/nassav/api/resource/{avid}")

    assert response.status_code == 200
    assert not AVResource.objects.filter(avid=avid).exists()
    assert not cover.exists()
    assert not video.exists()


def test_download_progress_round_trip_uses_fake_redis(monkeypatch):
    class FakeRedis:
        def __init__(self):
            self.values = {}

        def setex(self, key, ttl, value):
            assert ttl == 3600
            self.values[key] = value

        def get(self, key):
            return self.values.get(key)

    fake = FakeRedis()
    monkeypatch.setattr(tasks, "get_redis_client", lambda: fake)

    tasks.set_task_progress("p0-1", 42, speed="2MiB/s", eta="00:10")

    assert tasks.get_task_progress("P0-1")["percent"] == 42
    assert tasks.get_task_progress("P0-1")["speed"] == "2MiB/s"
    assert tasks.get_task_progress("P0-1")["eta"] == "00:10"


@pytest.mark.django_db(transaction=True)
def test_websocket_reconnect_receives_new_events(monkeypatch, settings, ws_headers):
    settings.CHANNEL_LAYERS = {
        "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
    }
    monkeypatch.setattr(
        tasks,
        "get_task_queue_status",
        lambda: {"active_tasks": [], "pending_tasks": []},
    )

    async def run():
        for version in (1, 2):
            communicator = WebsocketCommunicator(
                application, "/nassav/ws/tasks/", headers=ws_headers
            )
            connected, _ = await communicator.connect()
            assert connected
            await communicator.receive_json_from()
            await get_channel_layer().group_send(
                "task_updates",
                {
                    "type": "task_update",
                    "update_type": "progress_update",
                    "data": {"task_id": "p0-download", "version": version},
                },
            )
            event = await communicator.receive_json_from()
            assert event == {
                "type": "progress_update",
                "data": {"task_id": "p0-download", "version": version},
            }
            await communicator.disconnect()

    asyncio.run(run())


def test_sqlite_backup_uses_disposable_database_and_directory(tmp_path):
    backend_root = Path(__file__).resolve().parents[1]
    database = tmp_path / "p0.sqlite3"
    config = backend_root / "config" / "template-config.yaml"
    environment = os.environ.copy()
    environment.update(
        DJANGO_SETTINGS_MODULE="django_project.settings",
        DB_ENGINE="sqlite",
        DATABASE_PATH=str(database),
        NASSAV_CONFIG_PATH=str(config),
        SECRET_KEY="p0-test-only-secret",
    )
    script = (
        "from pathlib import Path; import django, sys; django.setup(); "
        "from django.conf import settings; "
        "from django.core.management import call_command; "
        "settings.BASE_DIR = Path(sys.argv[1]); "
        "call_command('migrate', verbosity=0, interactive=False); "
        "call_command('backup_database', verbosity=0)"
    )
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)],
        cwd=backend_root,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    backups = list((tmp_path / "backup").glob("database_*/db.sqlite3"))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM django_migrations").fetchone()[0]
            > 0
        )
