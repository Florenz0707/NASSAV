#!/usr/bin/env python3
"""Real Celery/Redis/native CLI acceptance against generated local media and isolated DB."""

import argparse
import hashlib
import http.server
import io
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from collections import Counter
from contextlib import ExitStack
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

BINARY_SHA256 = "d2fa5b4b79f243320c509a85835327a520d8c160c600d99921e764bfc519fec7"


def wait_for(read, condition, *, seconds=60, label="condition"):
    deadline = time.monotonic() + seconds
    last = None
    while time.monotonic() < deadline:
        last = read()
        if condition(last):
            return last
        time.sleep(0.1)
    raise RuntimeError(f"Timed out waiting for {label}: {last}")


def stop_fixture_process(process, group):
    if process.poll() is not None:
        return
    if group:
        os.killpg(process.pid, signal.SIGTERM)
    else:
        process.terminate()
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        if group:
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
        process.wait(timeout=5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--postgres-socket", type=Path)
    args = parser.parse_args()
    binary = args.binary.resolve()
    if hashlib.sha256(binary.read_bytes()).hexdigest() != BINARY_SHA256:
        parser.error("Acceptance requires the fixed P0 CLI binary")
    if args.postgres_socket and (
        not args.postgres_socket.resolve().is_relative_to("/tmp")
        or not args.postgres_socket.name.startswith("nassav-task-control-")
    ):
        parser.error(
            "PostgreSQL socket must belong to an isolated /tmp/nassav-task-control-* fixture"
        )
    backend = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(backend))
    from PIL import Image
    from scripts.probe_task_download_control import generate_media, decoded_hash

    workers = []
    redis_process = None
    server = None
    report = {
        "db": "postgresql" if args.postgres_socket else "sqlite",
        "binary_sha256": BINARY_SHA256,
        "cases": [],
        "status": "running",
        "source": "generated local HTTP fixtures",
    }
    with (
        tempfile.TemporaryDirectory(prefix="nassav-task-control-p7-") as temporary,
        ExitStack() as cleanup,
    ):
        root = Path(temporary)
        generate_media(root / "media")
        expected = decoded_hash(root / "media/index.m3u8")
        image_buffer = io.BytesIO()
        Image.new("RGB", (8, 8)).save(image_buffer, "JPEG")
        image = image_buffer.getvalue()
        requests = Counter()
        locks = threading.Lock()

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                parsed = urlsplit(self.path)
                avid = parse_qs(parsed.query).get("avid", [""])[0]
                with locks:
                    requests[(parsed.path, avid)] += 1
                if parsed.path.startswith("/media/"):
                    path = root / parsed.path.lstrip("/")
                    if path.suffix == ".ts":
                        time.sleep(0.4)
                    data = path.read_bytes()
                elif parsed.path == "/fixture/source":
                    data = b"<html>local source business page</html>"
                elif parsed.path == "/fixture/metadata":
                    data = json.dumps(
                        {
                            "title": f"Original {avid}",
                            "actors": ["Shared Actor", f"Actor {avid}"],
                            "genres": ["Local fixture"],
                        }
                    ).encode()
                else:
                    data = image
                    if (
                        parsed.path.endswith("cover") and avid == "P7-SCRAPE-PAUSE"
                    ) or (
                        parsed.path.endswith("avatar") and avid == "P7-SCRAPE-CANCEL"
                    ):
                        time.sleep(3)
                self.send_response(200)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                try:
                    self.wfile.write(data)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def do_POST(self):
                payload = json.loads(
                    self.rfile.read(int(self.headers["Content-Length"]))
                )
                data = json.dumps(
                    {"translated": "Translated " + payload["title"]}
                ).encode()
                with locks:
                    requests[("translation", payload["title"])] += 1
                self.send_response(200)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                try:
                    # Real curl callbacks observe controls before a delayed response finishes.
                    for start in range(0, len(data), 5):
                        self.wfile.write(data[start : start + 5])
                        self.wfile.flush()
                        time.sleep(0.2)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def log_message(self, *args):
                pass

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        server.daemon_threads = True
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        cleanup.callback(server.server_close)
        cleanup.callback(server.shutdown)
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            redis_port = reservation.getsockname()[1]
        redis_url = f"redis://127.0.0.1:{redis_port}/0"
        redis_log = (root / "redis.log").open("w")
        cleanup.callback(redis_log.close)
        redis_process = subprocess.Popen(
            [
                "redis-server",
                "--bind",
                "127.0.0.1",
                "--port",
                str(redis_port),
                "--save",
                "",
                "--appendonly",
                "no",
                "--dir",
                str(root),
            ],
            stdout=redis_log,
            stderr=subprocess.STDOUT,
        )
        cleanup.callback(stop_fixture_process, redis_process, False)
        import redis

        client = redis.from_url(redis_url, socket_timeout=2)
        cleanup.callback(client.close)

        def redis_ready():
            try:
                return client.ping()
            except redis.ConnectionError:
                return False

        wait_for(redis_ready, bool, seconds=5, label="isolated Redis")
        database = {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": str(root / "task.sqlite3"),
            "OPTIONS": {"timeout": 20},
        }
        if args.postgres_socket:
            database = {
                "ENGINE": "django.db.backends.postgresql",
                "NAME": "nassav_task_control",
                "USER": "postgres",
                "PASSWORD": "",
                "HOST": str(args.postgres_socket.resolve()),
                "PORT": "5432",
            }
        settings_text = f"""from django_project.refactoring_test_settings import *
from pathlib import Path
TASK_CONTROL_ACCEPTANCE = True
ALLOWED_HOSTS = ['testserver', '127.0.0.1']
NASSAV_REFACTORING_OFFLINE = False
P7_ROOT = {str(root)!r}
P7_BASE_URL = 'http://127.0.0.1:{server.server_port}'
P7_BINARY = {str(binary)!r}
DATABASES = {{'default': {database!r}}}
REDIS_URL = {redis_url!r}
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_TASK_ALWAYS_EAGER = False
CELERY_BROKER_CONNECTION_TIMEOUT = 2
CELERY_TASK_PUBLISH_RETRY = False
TASK_RECOVERY_INTERVAL = 5
RESOURCE_DIR = Path(P7_ROOT) / 'resource'
COVER_DIR = RESOURCE_DIR / 'cover'
AVATAR_DIR = RESOURCE_DIR / 'avatar'
VIDEO_DIR = RESOURCE_DIR / 'video'
THUMBNAIL_DIR = COVER_DIR / 'thumbnails'
LOG_DIR = Path(P7_ROOT) / 'logs'
"""
        (root / "p7_acceptance_settings.py").write_text(settings_text)
        sys.path.insert(0, str(root))
        sys.path.insert(0, str(backend / "tests"))
        os.environ["DJANGO_SETTINGS_MODULE"] = "p7_acceptance_settings"
        environment = {
            **os.environ,
            "PYTHONPATH": os.pathsep.join(
                [str(root), str(backend / "tests"), str(backend)]
            ),
            "COLUMNS": "120",
            "LINES": "40",
            "TERM": "xterm",
        }
        import django

        django.setup()
        from django.conf import settings
        from django.core.management import call_command
        from django.contrib.auth import get_user_model
        from django.db import close_old_connections
        from rest_framework.test import APIClient
        from nassav.models import AVResource
        from nassav.task_models import TaskAttempt, TaskEvent, TaskJob
        from nassav.task_processes import group_writers
        from nassav.task_records import DjangoTaskRecords
        from nassav.composition import build_task_recovery
        from django.utils import timezone
        from datetime import timedelta

        call_command("migrate", verbosity=0, interactive=False)
        user = get_user_model().objects.create_user(
            username=settings.NASSAV_OPERATOR_USERNAME
        )
        api = APIClient()
        api.force_authenticate(user)
        records = DjangoTaskRecords()
        for directory in (settings.COVER_DIR, settings.VIDEO_DIR, settings.AVATAR_DIR):
            directory.mkdir(parents=True, exist_ok=True)

        def stop_fixture_writers():
            from nassav.task_processes import stop_owned_writers

            for attempt in TaskAttempt.objects.exclude(execution_owner=None):
                if attempt.job.kind != "download" or not attempt.execution_identity.get(
                    "worker_start_ticks"
                ):
                    continue
                stop_owned_writers(
                    {
                        "job_id": str(attempt.job_id),
                        "attempt_id": str(attempt.id),
                        "owner": str(attempt.execution_owner),
                    },
                    attempt.execution_identity,
                )

        cleanup.callback(stop_fixture_writers)

        def start_worker(name, queue):
            log = (root / f"{name}-{len(workers)}.log").open("w")
            cleanup.callback(log.close)
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "celery",
                    "-A",
                    "task_control_worker_fixture:app",
                    "worker",
                    "--pool=prefork",
                    "--concurrency=1",
                    "--queues",
                    queue,
                    "--hostname",
                    name + "@%h",
                    "--loglevel=INFO",
                    "--without-gossip",
                    "--without-mingle",
                ],
                cwd=backend,
                env=environment,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            workers.append((process, log))
            cleanup.callback(stop_fixture_process, process, True)
            wait_for(
                lambda: (root / log.name).read_text(),
                lambda text: "ready." in text,
                seconds=20,
                label=f"{name} real worker ready",
            )
            return process

        def read(job):
            close_old_connections()
            return records.get(job["job_id"])

        def control(job, action):
            from uuid import uuid4

            for _ in range(20):
                snapshot = read(job)
                response = api.post(
                    f"/nassav/api/tasks/jobs/{job['job_id']}/{action}",
                    {
                        "expected_version": snapshot["version"],
                        "request_id": str(uuid4()),
                    },
                    format="json",
                )
                if response.status_code != 409:
                    assert response.status_code == 202, response.content
                    return response.json()["data"]
            raise RuntimeError("Repeated control version conflicts")

        def submit_download(avid):
            response = api.post(f"/nassav/api/downloads/{avid}")
            assert response.status_code == 202, response.content
            return records.get(response.json()["data"]["job_id"])

        def submit_scrape(avid):
            response = api.post(
                "/nassav/api/resource/jobs",
                {"avid": avid, "action": "add", "source": "any"},
                format="json",
            )
            assert response.status_code == 202, response.content
            return records.get(response.json()["data"]["job_id"])

        def state(job, expected_state, **kwargs):
            return wait_for(
                lambda: read(job),
                lambda j: j["state"] == expected_state,
                label=expected_state,
                **kwargs,
            )

        def download_started(job):
            def identity():
                attempt = TaskAttempt.objects.get(pk=read(job)["task_id"])
                return attempt.execution_identity

            return wait_for(
                identity, lambda i: bool(i.get("pid")), label="native CLI started"
            )

        def case(name, **details):
            report["cases"].append({"name": name, "passed": True, **details})
            print(f"PASS {name}", flush=True)

        try:
            download_worker = start_worker("p7-download", "download")
            start_worker("p7-scrape", "scrape")
            default_worker = start_worker("p7-default", "default")
            for avid in ("P7-DL-1", "P7-DL-2", "P7-DL-3"):
                AVResource.objects.create(
                    avid=avid, original_title=f"Existing {avid}", source="fixture"
                )
            first = submit_download("P7-DL-1")
            first_identity = download_started(first)
            private = settings.VIDEO_DIR / ".tasks" / first["job_id"] / "download"
            wait_for(
                lambda: list(private.glob("temp/*/*/*.ts")),
                lambda files: len(files) >= 2,
                label="partial segments",
            )
            before = time.monotonic()
            control(first, "pause")
            paused = state(first, "paused")
            stop_ms = round((time.monotonic() - before) * 1000)
            assert not group_writers(first_identity["pgid"])
            assert client.get("nassav:global_download_lock") is None
            assert list(private.glob("temp/*/*/*.ts"))
            case("download_pause_releases_capacity", stop_ms=stop_ms)
            original = settings.VIDEO_DIR / "P7-DL-2.mp4"
            original.write_bytes(b"Existing formal fixture video")
            second = submit_download("P7-DL-2")
            second_identity = download_started(second)
            control(second, "cancel")
            state(second, "cancelled")
            wait_for(
                lambda: read(second),
                lambda j: j["cleanup_state"] == "completed",
                label="download cleanup",
            )
            assert not group_writers(second_identity["pgid"])
            assert original.read_bytes() == b"Existing formal fixture video"
            case("cancel_preserves_formal_video_and_removes_private_files")
            resumed = control(first, "resume")
            assert (
                resumed["job_id"] == first["job_id"]
                and resumed["task_id"] != first["task_id"]
            )
            state(first, "succeeded")
            assert decoded_hash(settings.VIDEO_DIR / "P7-DL-1.mp4") == expected
            case(
                "real_cli_resume_matches_decoded_media",
                generation=resumed["generation"],
            )
            third = submit_download("P7-DL-3")
            orphan = download_started(third)
            os.killpg(download_worker.pid, signal.SIGKILL)
            download_worker.wait(timeout=5)
            assert group_writers(orphan["pgid"])
            control(third, "cancel")
            TaskAttempt.objects.filter(pk=third["task_id"]).update(
                heartbeat_at=timezone.now() - timedelta(seconds=60)
            )
            download_worker = start_worker("p7-download-restarted", "download")
            state(third, "cancelled")
            wait_for(
                lambda: read(third),
                lambda j: j["cleanup_state"] == "completed",
                label="automatic orphan cleanup",
            )
            assert not group_writers(orphan["pgid"])
            assert not (settings.VIDEO_DIR / ".tasks" / third["job_id"]).exists()
            case("worker_crash_orphan_group_recovery", automatic_worker_scan=True)
            AVResource.objects.create(
                avid="P7-DL-CLEANUP", original_title="Cleanup fixture", source="fixture"
            )
            cleanup_job = submit_download("P7-DL-CLEANUP")
            download_started(cleanup_job)
            control(cleanup_job, "pause")
            state(cleanup_job, "paused")
            workspace = settings.VIDEO_DIR / ".tasks" / cleanup_job["job_id"]
            workspace.chmod(0)
            try:
                control(cleanup_job, "cancel")
                assert read(cleanup_job)["state"] == "cancelled"
                assert read(cleanup_job)["cleanup_state"] == "failed"
            finally:
                workspace.chmod(0o700)
            control(cleanup_job, "cleanup_retry")
            assert read(cleanup_job)["cleanup_state"] == "completed"
            assert not workspace.exists()
            case("real_directory_permission_failure_and_cleanup_retry")

            (root / "fail-event").touch()
            scrape = submit_scrape("P7-SCRAPE-PAUSE")
            wait_for(
                lambda: read(scrape),
                lambda j: j["stage"] == "cover",
                label="scrape cover network",
            )
            control(scrape, "pause")
            state(scrape, "paused")
            assert not AVResource.objects.filter(avid=scrape["avid"]).exists()
            control(scrape, "resume")
            wait_for(
                lambda: read(scrape),
                lambda j: j["stage"] == "translation_translating",
                label="owned translation",
            )
            assert read(scrape)["resource_saved"]
            control(scrape, "pause")
            paused = state(scrape, "paused")
            assert paused["translation"]["state"] == "paused"
            resource = AVResource.objects.get(avid=scrape["avid"])
            assert (
                resource.translation_status == "pending"
                and resource.translated_title is None
            )
            assert TaskEvent.objects.get(job_id=scrape["job_id"]).state == "pending"
            (root / "fail-event").unlink()
            build_task_recovery().scan()
            assert TaskEvent.objects.get(job_id=scrape["job_id"]).state == "sent"
            control(scrape, "resume")
            done = state(scrape, "succeeded")
            resource.refresh_from_db()
            assert done["translation"]["state"] == "completed"
            assert resource.translated_title == f"Translated Original {scrape['avid']}"
            assert requests[("/fixture/source", scrape["avid"])] == 1
            case(
                "scrape_checkpoints_and_owned_translation_pause_resume",
                generation=done["generation"],
            )
            shared = settings.AVATAR_DIR / "Shared Actor.jpg"
            shared_bytes = shared.read_bytes()
            cancel_scrape = submit_scrape("P7-SCRAPE-CANCEL")
            wait_for(
                lambda: read(cancel_scrape),
                lambda j: j["stage"] == "avatars",
                label="private avatar network",
            )
            control(cancel_scrape, "cancel")
            state(cancel_scrape, "cancelled")
            wait_for(
                lambda: read(cancel_scrape),
                lambda j: j["cleanup_state"] == "completed",
                label="scrape cleanup",
            )
            assert not AVResource.objects.filter(avid=cancel_scrape["avid"]).exists()
            assert shared.read_bytes() == shared_bytes
            assert all(
                not (directory / ".tasks" / cancel_scrape["job_id"]).exists()
                for directory in (
                    settings.COVER_DIR,
                    settings.AVATAR_DIR,
                    settings.VIDEO_DIR,
                )
            )
            case("scrape_cancel_discards_private_images_preserves_shared_avatar")
            translation_crash = submit_scrape("P7-SCRAPE-CRASH")
            wait_for(
                lambda: read(translation_crash),
                lambda j: j["stage"] == "translation_translating",
                label="translation crash window",
            )
            child_attempt = read(translation_crash)["task_id"]
            committed_cover = settings.COVER_DIR / (translation_crash["avid"] + ".jpg")
            cover_bytes = committed_cover.read_bytes()
            os.killpg(default_worker.pid, signal.SIGKILL)
            default_worker.wait(timeout=5)
            control(translation_crash, "cancel")
            TaskAttempt.objects.filter(pk=child_attempt).update(
                heartbeat_at=timezone.now() - timedelta(seconds=60)
            )
            start_worker("p7-default-restarted", "default")
            state(translation_crash, "cancelled")
            wait_for(
                lambda: read(translation_crash),
                lambda j: j["cleanup_state"] == "completed",
                label="translation crash cleanup",
            )
            kept = AVResource.objects.get(avid=translation_crash["avid"])
            assert (
                kept.translated_title is None and kept.translation_status == "pending"
            )
            assert committed_cover.read_bytes() == cover_bytes
            assert read(translation_crash)["translation"]["state"] == "cancelled"
            case("translation_worker_crash_cancel_preserves_committed_resource")

            redis_process.terminate()
            redis_process.wait(timeout=5)
            AVResource.objects.create(
                avid="P7-DL-BROKER", original_title="Broker fixture", source="fixture"
            )
            broker_job = submit_download("P7-DL-BROKER")
            assert TaskAttempt.objects.get(pk=broker_job["task_id"]).state == "pending"
            redis_process = subprocess.Popen(
                [
                    "redis-server",
                    "--bind",
                    "127.0.0.1",
                    "--port",
                    str(redis_port),
                    "--save",
                    "",
                    "--appendonly",
                    "no",
                    "--dir",
                    str(root),
                ],
                stdout=redis_log,
                stderr=subprocess.STDOUT,
            )
            cleanup.callback(stop_fixture_process, redis_process, False)
            wait_for(
                redis_ready, bool, seconds=5, label="restarted actual Redis broker"
            )
            state(broker_job, "succeeded", seconds=90)
            case("real_broker_outage_pending_dispatch_recovers_without_browser")

            assert (
                TaskJob.objects.filter(
                    state__in=["queued", "running", "pausing", "cancelling"]
                ).count()
                == 0
            )
            assert TaskAttempt.objects.filter(state="running").count() == 0
            assert client.get("nassav:global_download_lock") is None
            report["status"] = "passed"
        except Exception as error:
            report["status"] = "failed"
            report["error"] = str(error)
            for _, log in workers:
                log.flush()
                print(Path(log.name).read_text()[-12000:], file=sys.stderr)
            raise
        finally:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\n"
            )
            close_old_connections()


if __name__ == "__main__":
    main()
