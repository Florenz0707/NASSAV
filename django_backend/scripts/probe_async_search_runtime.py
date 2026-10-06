"""Isolated live acceptance for Chinese listings, images, settings and Celery.

Usage: PYTHONPATH=/app python scripts/probe_async_search_runtime.py
Optional: --fetch-pages 1..5 (default 1), --cases missav-genre jable-genre ...
With multiple pages, requires a running partial snapshot before completion.
Requires DB=/tmp/nassav-external-search-acceptance.sqlite3 and isolated Redis
host nassav-external-search-test-redis. Creates disposable rows and a worker.
Stops on the first failure. Outputs only counts, states and timings.
"""

import argparse
import asyncio
import json
import os
import subprocess
import sys
import threading
import time
from urllib.parse import urlsplit

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "django_project.settings")
from django.conf import settings

if (
    str(settings.DATABASES["default"]["NAME"])
    != "/tmp/nassav-external-search-acceptance.sqlite3"
    or urlsplit(settings.REDIS_URL).hostname != "nassav-external-search-test-redis"
):
    raise RuntimeError("This probe requires the disposable database and Redis")

import django

django.setup()
from channels.layers import get_channel_layer
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client
from nassav.models import (
    Actor,
    ActorSourceMapping,
    Genre,
    GenreSourceMapping,
)
from nassav.user_settings import clear_settings_manager_cache


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


class SearchNotifications:
    """Observe Redis events continuously so fast page transitions are not missed."""

    def __init__(self):
        self.condition = threading.Condition()
        self.events = []
        self.ready = threading.Event()
        self.stopped = threading.Event()
        self.thread = threading.Thread(
            target=lambda: asyncio.run(self.receive()), daemon=True
        )
        self.thread.start()
        require(self.ready.wait(10), "Redis notification listener did not start")

    async def receive(self):
        layer = get_channel_layer()
        channel = await layer.new_channel("search_probe.")
        await layer.group_add("task_updates", channel)
        self.ready.set()
        try:
            while not self.stopped.is_set():
                try:
                    event = await asyncio.wait_for(layer.receive(channel), timeout=0.5)
                except TimeoutError:
                    continue
                if event.get("update_type") == "external_search_update":
                    with self.condition:
                        self.events.append(event["data"])
                        self.condition.notify_all()
        finally:
            await layer.group_discard("task_updates", channel)

    def wait(self, task_id, version):
        with self.condition:
            self.condition.wait_for(
                lambda: any(
                    event["task_id"] == task_id and event["version"] > version
                    for event in self.events
                ),
                timeout=1,
            )

    def versions(self, task_id):
        with self.condition:
            events = [event for event in self.events if event["task_id"] == task_id]
            require(
                all(
                    set(event) == {"task_id", "state", "version", "updated_at"}
                    for event in events
                ),
                "Unexpected socket payload",
            )
            return [event["version"] for event in events]

    def close(self):
        self.stopped.set()
        self.thread.join(timeout=2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch-pages", type=int, choices=range(1, 6), default=1)
    parser.add_argument(
        "--cases",
        nargs="+",
        choices=[
            "missav-genre",
            "missav-actor",
            "missav-keyword",
            "jable-genre",
            "jable-actor",
        ],
    )
    args = parser.parse_args()
    settings.EXTERNAL_SEARCH_FETCH_PAGES = args.fetch_pages
    settings.EXTERNAL_SEARCH_CACHE_ENABLED = True
    call_command("migrate", verbosity=0)
    user, _ = get_user_model().objects.get_or_create(
        username=settings.NASSAV_OPERATOR_USERNAME
    )
    actor, _ = Actor.objects.get_or_create(name="波多野結衣")
    genre, _ = Genre.objects.get_or_create(name="VR")
    ActorSourceMapping.objects.update_or_create(
        actor=actor, source_name="missav", defaults={"source_actor_slug": actor.name}
    )
    GenreSourceMapping.objects.update_or_create(
        genre=genre, source_name="missav", defaults={"source_genre_slug": genre.name}
    )
    client = Client()
    client.force_login(user)
    updated = client.put(
        "/nassav/api/setting",
        {"default_external_search_source": "missav"},
        content_type="application/json",
    )
    require(updated.status_code == 200, "Setting update failed")
    clear_settings_manager_cache()
    require(
        client.get("/nassav/api/setting").json()["data"][
            "default_external_search_source"
        ]
        == "missav",
        "Setting did not persist",
    )
    notifications = SearchNotifications()
    worker_log = open("/tmp/search-worker.log", "w")
    worker_code = f"from django.conf import settings; settings.EXTERNAL_SEARCH_FETCH_PAGES={args.fetch_pages}; settings.EXTERNAL_SEARCH_CACHE_ENABLED=True; from django_project.celery import app; app.worker_main(['worker','-Q','scrape','--concurrency=1','--pool=solo','--loglevel=WARNING','--without-gossip','--without-mingle','--without-heartbeat'])"
    worker = subprocess.Popen(
        [sys.executable, "-c", worker_code], stdout=worker_log, stderr=worker_log
    )
    try:
        for source, entity, obj, keyword in [
            ("missav", "genre", genre, False),
            ("missav", "actor", actor, False),
            ("missav", "actor", actor, True),
            ("jable", "genre", genre, False),
            ("jable", "actor", actor, False),
        ]:
            case = f"{source}-{'keyword' if keyword else entity}"
            if args.cases and case not in args.cases:
                continue
            if keyword:
                ActorSourceMapping.objects.filter(
                    actor=actor, source_name="missav"
                ).delete()
            query = {
                "entity_type": entity,
                "entity_id": obj.pk,
                "source": source,
                "force_refresh": True,
            }
            started = time.monotonic()
            response = client.post(
                "/nassav/api/search/jobs", query, content_type="application/json"
            )
            submit_seconds = time.monotonic() - started
            require(
                response.status_code == 202,
                f"Submission failed: {source}/{entity} HTTP {response.status_code}",
            )
            require(submit_seconds < 2, "Submission exceeded 2 seconds")
            job = response.json()["data"]
            repeated = client.post(
                "/nassav/api/search/jobs", query, content_type="application/json"
            )
            require(
                repeated.json()["data"]["task_id"] == job["task_id"],
                "Running search was not deduplicated",
            )
            first_result_seconds = None
            progress_versions = []
            deadline = time.monotonic() + 400
            while time.monotonic() < deadline:
                require(worker.poll() is None, "Worker stopped")
                polled = client.get(
                    f"/nassav/api/search/jobs/{job['task_id']}", {"token": job["token"]}
                )
                require(polled.status_code == 200, "Polling failed")
                snapshot = polled.json()["data"]
                if snapshot["state"] == "running" and snapshot.get("result"):
                    require(
                        snapshot["result"]["data"]["external_meta"]["partial"],
                        "Running result must be partial",
                    )
                    if first_result_seconds is None:
                        first_result_seconds = time.monotonic() - started
                    if snapshot["version"] not in progress_versions:
                        progress_versions.append(snapshot["version"])
                if snapshot["state"] in {"failed", "succeeded"}:
                    break
                notifications.wait(job["task_id"], snapshot["version"])
            require(
                snapshot["state"] == "succeeded",
                f"{source}/{entity} search failed: {snapshot.get('error_code')}",
            )
            require(
                not snapshot["result"]["data"]["external_meta"]["partial"],
                "Final result is still partial",
            )
            if args.fetch_pages > 1:
                require(bool(progress_versions), "No running page result was observed")
            notifications.wait(job["task_id"], snapshot["version"] - 1)
            event_versions = notifications.versions(job["task_id"])
            require(
                snapshot["version"] in event_versions,
                "Terminal Redis notification missing",
            )
            require(
                set(progress_versions).issubset(event_versions),
                "Page Redis notification missing",
            )
            items = snapshot["result"]["data"]["external_results"]
            require(bool(items), "Search returned no cards")
            if source == "missav":
                require(
                    all("/cn/" in item["detail_url"] for item in items),
                    "Results are not Chinese URLs",
                )
            image = client.get(
                "/nassav/api/recommendations/cover",
                {"source": source, "url": items[0]["thumbnail_url"]},
            )
            require(
                image.status_code == 200 and image["Content-Type"].startswith("image/"),
                f"Image proxy failed: HTTP {image.status_code}",
            )
            image_bytes = sum(len(chunk) for chunk in image.streaming_content)
            require(image_bytes > 100, "Empty image")
            image.close()
            print(
                json.dumps(
                    {
                        "source": source,
                        "entity": entity,
                        "keyword": keyword,
                        "state": snapshot["state"],
                        "count": len(items),
                        "fetch_pages": args.fetch_pages,
                        "first_result_seconds": round(first_result_seconds, 2)
                        if first_result_seconds is not None
                        else None,
                        "progress_versions": progress_versions,
                        "event_versions": event_versions,
                        "submit_seconds": round(submit_seconds, 3),
                        "total_seconds": round(time.monotonic() - started, 2),
                        "image_status": 200,
                        "image_bytes": image_bytes,
                    }
                ),
                flush=True,
            )
    finally:
        notifications.close()
        worker.terminate()
        try:
            worker.wait(timeout=10)
        except subprocess.TimeoutExpired:
            worker.kill()
            worker.wait()
        worker_log.close()


if __name__ == "__main__":
    main()
