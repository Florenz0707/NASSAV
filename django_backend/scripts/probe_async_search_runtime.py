"""Isolated live acceptance for Chinese listings, images, settings and Celery.

Usage: PYTHONPATH=/app python scripts/probe_async_search_runtime.py
Requires DB=/tmp/nassav-external-search-acceptance.sqlite3 and isolated Redis
host nassav-external-search-test-redis. Creates disposable rows and a worker.
Stops on the first failure. Outputs only counts, states and timings.
"""

import json
import os
import subprocess
import sys
import time
from urllib.parse import urlsplit

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "django_project.settings")
from django.conf import settings  # noqa: E402

if (
    str(settings.DATABASES["default"]["NAME"])
    != "/tmp/nassav-external-search-acceptance.sqlite3"
    or urlsplit(settings.REDIS_URL).hostname != "nassav-external-search-test-redis"
):
    raise RuntimeError("This probe requires the disposable database and Redis")

import django  # noqa: E402

django.setup()
from django.core.management import call_command  # noqa: E402
from django.contrib.auth import get_user_model  # noqa: E402
from django.test import Client  # noqa: E402
from nassav.models import Actor, Genre, ActorSourceMapping, GenreSourceMapping  # noqa: E402
from nassav.user_settings import clear_settings_manager_cache  # noqa: E402


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    settings.EXTERNAL_SEARCH_FETCH_PAGES = 1
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
    worker_log = open("/tmp/search-worker.log", "w")
    worker_code = "from django.conf import settings; settings.EXTERNAL_SEARCH_FETCH_PAGES=1; settings.EXTERNAL_SEARCH_CACHE_ENABLED=True; from django_project.celery import app; app.worker_main(['worker','-Q','scrape','--concurrency=1','--pool=solo','--loglevel=WARNING','--without-gossip','--without-mingle','--without-heartbeat'])"
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
            deadline = time.monotonic() + 400
            while time.monotonic() < deadline:
                require(worker.poll() is None, "Worker stopped")
                polled = client.get(
                    f"/nassav/api/search/jobs/{job['task_id']}", {"token": job["token"]}
                )
                require(polled.status_code == 200, "Polling failed")
                snapshot = polled.json()["data"]
                if snapshot["state"] in {"failed", "succeeded"}:
                    break
                time.sleep(1)
            require(
                snapshot["state"] == "succeeded",
                f"{source}/{entity} search failed: {snapshot.get('error_code')}",
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
                        "submit_seconds": round(submit_seconds, 3),
                        "total_seconds": round(time.monotonic() - started, 2),
                        "image_status": 200,
                        "image_bytes": image_bytes,
                    }
                ),
                flush=True,
            )
    finally:
        worker.terminate()
        try:
            worker.wait(timeout=10)
        except subprocess.TimeoutExpired:
            worker.kill()
            worker.wait()
        worker_log.close()


if __name__ == "__main__":
    main()
