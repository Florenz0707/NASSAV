"""Opt-in loopback MP4 server with disposable DB, user, Redis and media."""

import json
import os
import subprocess
import tempfile
from pathlib import Path


def main():
    if os.environ.get("NASSAV_LOCAL_PLAYBACK_TEST_SERVER") != "1":
        raise SystemExit(
            "Opt in with NASSAV_LOCAL_PLAYBACK_TEST_SERVER=1; isolated data only"
        )

    os.environ["DJANGO_SETTINGS_MODULE"] = "django_project.refactoring_test_settings"
    import django

    django.setup()
    from django.conf import settings
    from django.core.management import call_command
    from django.contrib.auth import get_user_model
    from django.test import Client
    from nassav.models import AVResource

    fixture = tempfile.TemporaryDirectory(prefix="nassav-local-playback-http-")
    root = Path(fixture.name)
    settings.PLAYBACK_ENABLED = True
    settings.PLAYBACK_ALLOWED_HOSTS = ()
    settings.PROXY_ENABLED = False
    settings.CELERY_BROKER_URL = "unix://" + str(root / "redis.sock") + "?db=0"
    settings.DATABASES["default"]["NAME"] = str(root / "database.sqlite3")
    settings.VIDEO_DIR = root / "resource/video"
    settings.COVER_DIR = root / "resource/cover"
    settings.AVATAR_DIR = root / "resource/avatar"
    for path in [settings.VIDEO_DIR, settings.COVER_DIR, settings.AVATAR_DIR]:
        path.mkdir(parents=True)
    call_command("migrate", verbosity=0)
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=640x360:rate=24",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=44100",
            "-t",
            "90",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            "-g",
            "48",
            "-c:a",
            "aac",
            "-b:a",
            "64k",
            str(settings.VIDEO_DIR / "LOCAL-PLAYBACK.mp4"),
        ],
        check=True,
    )
    AVResource.objects.create(
        avid="LOCAL-PLAYBACK",
        source="Jable",
        original_title="已下载视频隔离验收",
        file_exists=True,
        file_size=(settings.VIDEO_DIR / "LOCAL-PLAYBACK.mp4").stat().st_size,
    )
    user = get_user_model().objects.create_user(
        username=settings.NASSAV_OPERATOR_USERNAME
    )
    client = Client()
    client.force_login(user)
    assert (
        client.get("/nassav/api/auth/session", HTTP_HOST="127.0.0.1:9791").status_code
        == 200
    )
    state = {
        "cookies": [
            {
                "name": m.key,
                "value": m.value,
                "domain": "127.0.0.1",
                "path": "/",
                "expires": -1,
                "httpOnly": bool(m["httponly"]),
                "secure": False,
                "sameSite": "Lax",
            }
            for m in client.cookies.values()
        ],
        "origins": [],
    }
    p = root / "storage-state.json"
    p.write_text(json.dumps(state))
    p.chmod(0o600)
    print("ISOLATED_STORAGE_STATE=" + str(p), flush=True)
    redis_log = (root / "redis.log").open("w")
    redis = subprocess.Popen(
        [
            "redis-server",
            "--port",
            "0",
            "--unixsocket",
            str(root / "redis.sock"),
            "--unixsocketperm",
            "700",
            "--save",
            "",
            "--appendonly",
            "no",
        ],
        stdout=redis_log,
        stderr=subprocess.STDOUT,
    )
    try:
        import time

        for _ in range(100):
            if (root / "redis.sock").exists():
                break
            time.sleep(0.02)
        import uvicorn
        from django_project.asgi import application

        uvicorn.run(
            application,
            host="127.0.0.1",
            port=9791,
            log_level="warning",
            access_log=False,
        )
    finally:
        redis.terminate()
        redis.wait(timeout=5)
        redis_log.close()
        from django.db import connections

        connections.close_all()
        fixture.cleanup()


if __name__ == "__main__":
    main()
