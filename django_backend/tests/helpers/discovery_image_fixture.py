"""Explicit synthetic result ledger and prefilled scoped image for native UI tests."""

import json
import os
from datetime import timedelta
from pathlib import Path
from uuid import uuid4


def install(settings, root, user):
    if os.environ.get("NASSAV_DISCOVERY_IMAGE_UI_TEST_FIXTURE") != "1":
        raise RuntimeError("Discovery image fixture requires explicit opt-in")
    if (
        not settings.SHARED_LIBRARY_ENABLED
        or Path(settings.DATABASES["default"]["NAME"]) != root / "database.sqlite3"
    ):
        raise RuntimeError("Disposable shared library fixture required")
    from django.utils import timezone
    from PIL import Image, ImageDraw
    from nassav import composition
    from nassav.account_policy import execution_epoch
    from nassav.models import RecommendationSnapshot, RecommendationItem
    from nassav.recommendation_models import RecommendationJob
    from nassav.recommendation.jobs import history_generation
    from nassav.recommendation.images import source_image_context
    from nassav.recommendation.cover_cache import RecommendationCoverCacheService
    from nassav.search_jobs import RedisSearchJobStore, search_job_token

    settings.SOURCE_CONFIG = {
        **settings.SOURCE_CONFIG,
        "jable": {**settings.SOURCE_CONFIG.get("jable", {}), "weight": 1},
    }
    settings.RECOMMENDATION_COVER_DIR = root / "resource/recommendation"
    source = composition.source_factories(
        None, settings.BROWSER_FETCH_CONFIG, lambda *args: None, user_id=user.pk
    )["jable"]()
    try:
        proof = source_image_context(source)
        url = "https://assets-cdn.jable.tv/nassav-isolated/cover.png"
        path = RecommendationCoverCacheService(source).get_cache_path(url)
        path.parent.mkdir(parents=True, exist_ok=True)
        image = Image.new("RGB", (320, 180), (45, 57, 80))
        ImageDraw.Draw(image).text((70, 80), "ISOLATED IMAGE", fill=(220, 230, 240))
        image.save(path, format="PNG")
    finally:
        if source.page_fetcher.browser is not None:
            source.page_fetcher.browser.close()
    snapshot = RecommendationSnapshot.objects.create(
        owner=user,
        recommender_id="jable_page_lookup",
        strategy_id="local_preference",
        request_fingerprint="isolated-image-ui",
        request_payload={"_image_contexts_v1": {"jable": proof}},
    )
    item = RecommendationItem.objects.create(
        snapshot=snapshot,
        rank=1,
        avid="IMAGE-UI",
        title="图片授权隔离验收",
        source="Jable",
        cover_url=url,
    )
    result = {
        "items": [
            {
                "snapshot_id": snapshot.pk,
                "avid": item.avid,
                "title": item.title,
                "source": item.source,
                "cover_url": url,
            }
        ],
        "meta": {"snapshot_id": snapshot.pk},
    }
    job = RecommendationJob.objects.create(
        owner=user,
        state="succeeded",
        history_generation=history_generation(user.pk),
        result=result,
        deadline=timezone.now() + timedelta(minutes=5),
    )
    task_id = str(uuid4())
    row = {
        "avid": item.avid,
        "source_title": item.title,
        "source": "Jable",
        "thumbnail_url": url,
    }
    import time

    search = {
        "task_id": task_id,
        "owner_id": user.pk,
        "owner_epoch": execution_epoch(user.pk),
        "job_type": "external_search",
        "state": "succeeded",
        "query_key": "isolated-image-ui",
        "query": {
            "source": "jable",
            "catalog_namespace": "owned-catalog-v1",
            "source_context": proof,
            "force_refresh": True,
            "entity_type": "actor",
            "entity_id": 1,
        },
        "collected_results": [row],
        "result": {
            "data": {"external_results": [row]},
            "pagination": {"page": 1, "page_size": 20, "total": 1, "pages": 1},
        },
        "submitted_at": time.time(),
        "completed_at": time.time(),
        "message": None,
        "error_code": None,
    }
    RedisSearchJobStore().save(search)
    manifest = root / "discovery-image-fixture.json"
    manifest.write_text(
        json.dumps(
            {
                "job_id": str(job.pk),
                "task_id": task_id,
                "token": search_job_token(task_id, user_id=user.pk),
            }
        )
    )
    manifest.chmod(0o600)
    print("ISOLATED_DISCOVERY_IMAGE_FIXTURE=" + str(manifest), flush=True)
