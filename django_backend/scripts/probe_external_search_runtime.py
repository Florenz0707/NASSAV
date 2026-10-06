"""Exercise actor/genre APIs against real sources in a disposable runtime.

Usage: PYTHONPATH=/app python scripts/probe_external_search_runtime.py --fetch-pages 1
Optional: --source missav --entity actor --keyword.
Requires the exact isolated SQLite path and Redis hostname checked below.
Writes only disposable DB rows. Outputs sanitized counts, statuses and timings.
"""

import argparse
import base64
import json
import os
from pathlib import Path
from time import monotonic
from urllib.parse import urlsplit

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "django_project.settings")
from django.conf import settings

if (
    str(settings.DATABASES["default"]["NAME"])
    != "/tmp/nassav-external-search-acceptance.sqlite3"
    or urlsplit(settings.REDIS_URL).hostname != "nassav-external-search-test-redis"
):
    raise RuntimeError(
        "This probe requires the disposable acceptance database and Redis"
    )
settings.LOG_DIR = Path("/tmp/search-log")
settings.LOG_DIR.mkdir(exist_ok=True)
import django

django.setup()
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client
from nassav.models import (
    Actor,
    ActorSourceMapping,
    Genre,
    GenreSourceMapping,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch-pages", type=int, default=1)
    parser.add_argument("--source", choices=("missav", "jable"))
    parser.add_argument("--entity", choices=("actor", "genre"))
    parser.add_argument(
        "--keyword", action="store_true", help="Use name search without MissAV mappings"
    )
    args = parser.parse_args()
    if not 1 <= args.fetch_pages <= 2:
        parser.error("--fetch-pages must be 1 or 2")
    call_command("migrate", verbosity=0)
    settings.EXTERNAL_SEARCH_FETCH_PAGES = args.fetch_pages
    settings.EXTERNAL_SEARCH_CACHE_ENABLED = True
    settings.EXTERNAL_SOURCE_SEARCH_CACHE_ENABLED = False
    user, _ = get_user_model().objects.get_or_create(username="acceptance")
    actor, _ = Actor.objects.get_or_create(name="波多野結衣")
    genre, _ = Genre.objects.get_or_create(name="VR")
    ActorSourceMapping.objects.update_or_create(
        actor=actor, source_name="missav", defaults={"source_actor_slug": actor.name}
    )
    GenreSourceMapping.objects.update_or_create(
        genre=genre, source_name="missav", defaults={"source_genre_slug": "VR"}
    )
    if args.keyword:
        ActorSourceMapping.objects.filter(actor=actor, source_name="missav").delete()
        GenreSourceMapping.objects.filter(genre=genre, source_name="missav").delete()
    client = Client()
    client.force_login(user)
    options = client.get("/nassav/api/source/search-capabilities")
    print(
        json.dumps(
            {
                "stage": "capabilities",
                "status": options.status_code,
                "sources": [row["source"] for row in options.json().get("data", [])],
            }
        ),
        flush=True,
    )
    from redis import Redis

    queue_store = Redis.from_url(settings.REDIS_URL)
    failures = 0
    for source in (args.source,) if args.source else ("missav", "jable"):
        for entity, obj in (("actor", actor), ("genre", genre)):
            if args.entity and args.entity != entity:
                continue
            started = monotonic()
            response = client.get(
                f"/nassav/api/{'actors' if entity == 'actor' else 'genres'}/{obj.pk}/detail",
                {"source": source, "ordering": "-views", "force_refresh": True},
            )
            data = response.json().get("data") or {}
            items = data.get("external_results") or []
            valid = (
                response.status_code == 200
                and bool(items)
                and all(
                    row["source"].lower() == source
                    and row["avid"]
                    and row["detail_url"]
                    for row in items
                )
            )
            print(
                json.dumps(
                    {
                        "stage": "search",
                        "source": source,
                        "entity": entity,
                        "status": response.status_code,
                        "valid": valid,
                        "items": len(items),
                        "elapsed_seconds": round(monotonic() - started, 3),
                        "failure": response.json().get("message")
                        if not valid
                        else None,
                    }
                ),
                flush=True,
            )
            failures += not valid
            if not valid:
                # Stop at the first acceptance failure, as requested.
                return 2
            admission = client.post(
                "/nassav/api/resource/jobs",
                data={
                    "action": "add",
                    "avid": items[0]["avid"],
                    "source": source,
                },
                content_type="application/json",
            )
            job = (admission.json().get("data") or {}).get("job") or {}
            queued_source = None
            for raw in queue_store.lrange("scrape", 0, -1):
                message = json.loads(raw)
                if message.get("headers", {}).get("id") == job.get("task_id"):
                    task_args = json.loads(base64.b64decode(message["body"]))[0]
                    queued_source = task_args[2]
                    break
            accepted = admission.status_code == 202 and queued_source == source
            print(
                json.dumps(
                    {
                        "stage": "admission",
                        "source": source,
                        "entity": entity,
                        "status": admission.status_code,
                        "source_preserved": accepted,
                    }
                ),
                flush=True,
            )
            if not accepted:
                return 2
            cached = client.get(
                f"/nassav/api/{'actors' if entity == 'actor' else 'genres'}/{obj.pk}/detail",
                {"source": source, "ordering": "-views"},
            )
            hit = (
                (cached.json().get("data") or {})
                .get("external_meta", {})
                .get("cache", {})
                .get("hit", False)
            )
            print(
                json.dumps(
                    {
                        "stage": "cache",
                        "source": source,
                        "entity": entity,
                        "status": cached.status_code,
                        "hit": hit,
                    }
                ),
                flush=True,
            )
            if cached.status_code != 200 or not hit:
                return 2
    return 2 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
