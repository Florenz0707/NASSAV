from datetime import timedelta

import pytest
from django.utils import timezone


@pytest.mark.django_db
def test_recommendations_options_endpoint(api_client):
    response = api_client.get("/nassav/api/recommendations/options")
    assert response.status_code == 200

    body = response.json()
    assert body["code"] == 200
    assert body["data"]["defaults"]["recommender"] == "jable_search"
    assert body["data"]["defaults"]["strategy"] == "local_preference"
    assert any(item["id"] == "jable_search" for item in body["data"]["recommenders"])
    assert any(item["id"] == "local_preference" for item in body["data"]["strategies"])
    assert any(item["id"] == "balanced" for item in body["data"]["strategies"])
    assert any(item["id"] == "actor_heavy" for item in body["data"]["strategies"])
    assert any(item["id"] == "recent_favorite" for item in body["data"]["strategies"])
    local_preference = next(
        item for item in body["data"]["strategies"] if item["id"] == "local_preference"
    )
    assert local_preference["default_request_overrides"]["limit"] == 12


@pytest.mark.django_db
def test_recommendations_endpoint_runs_with_empty_search(
    api_client, monkeypatch, resource_factory, actor_factory, genre_factory
):
    from nassav.source import Jable

    actor = actor_factory(name="Alice")
    genre = genre_factory(name="中文字幕")

    resource = resource_factory(avid="SEED-001", original_title="Seed Resource")
    resource.actors.add(actor)
    resource.genres.add(genre)

    monkeypatch.setattr(Jable, "search", lambda self, keyword, page=1: [])

    response = api_client.get("/nassav/api/recommendations/")
    assert response.status_code == 200

    body = response.json()
    assert body["code"] == 200
    assert body["data"]["meta"]["recommender"] == "jable_search"
    assert body["data"]["meta"]["strategy"] == "local_preference"
    assert body["data"]["meta"]["snapshot_id"] is not None
    assert body["data"]["meta"]["request_fingerprint"]
    assert body["data"]["meta"]["recommender_detail"]["name"] == "Jable Search"
    assert "Jable" in body["data"]["meta"]["strategy_detail"]["description"]
    assert body["data"]["meta"]["effective_request"]["limit"] == 12
    assert body["data"]["meta"]["effective_request"]["exclude_existing"] is True
    assert (
        body["data"]["meta"]["effective_request"]["avoid_recent_recommendations"]
        is True
    )
    assert "items" in body["data"]
    assert "seeds" in body["data"]
    assert body["data"]["summary"]["seed_count"] >= 2
    assert body["data"]["items"] == []


@pytest.mark.django_db
def test_recommendations_endpoint_merges_scores_and_filters_existing(
    api_client,
    monkeypatch,
    resource_factory,
    actor_factory,
    genre_factory,
):
    from nassav.source import Jable

    actor = actor_factory(name="Alice")
    genre = genre_factory(name="中文字幕")

    seed_resource_1 = resource_factory(avid="SEED-101", original_title="Seed One")
    seed_resource_1.actors.add(actor)
    seed_resource_1.genres.add(genre)

    seed_resource_2 = resource_factory(avid="SEED-102", original_title="Seed Two")
    seed_resource_2.actors.add(actor)

    resource_factory(avid="REC-002", original_title="Existing Recommended")

    def fake_search(self, keyword, page=1):
        _ = self
        _ = page
        if keyword == "Alice":
            return [
                {
                    "avid": "REC-001",
                    "title": "Alice Result",
                    "detail_url": "https://jable.tv/videos/rec-001/",
                    "cover_url": "https://img/rec-001.jpg",
                    "metrics": {"views": 1000000, "likes": 2000},
                },
                {
                    "avid": "REC-002",
                    "title": "Existing Result",
                    "detail_url": "https://jable.tv/videos/rec-002/",
                    "cover_url": "https://img/rec-002.jpg",
                    "metrics": {"views": 100, "likes": 10},
                },
            ]
        if keyword == "中文字幕":
            return [
                {
                    "avid": "REC-001",
                    "title": "Genre Result",
                    "detail_url": "https://jable.tv/videos/rec-001/",
                    "cover_url": "https://img/rec-001.jpg",
                    "metrics": {"views": 500000, "likes": 3000},
                }
            ]
        return []

    monkeypatch.setattr(Jable, "search", fake_search)

    response = api_client.get(
        "/nassav/api/recommendations/",
        {
            "recommender": "jable_search",
            "strategy": "local_preference",
            "actor_seed_limit": 1,
            "genre_seed_limit": 1,
            "per_seed_limit": 10,
        },
    )
    assert response.status_code == 200

    body = response.json()
    assert body["code"] == 200

    items = body["data"]["items"]
    assert len(items) == 1
    assert items[0]["avid"] == "REC-001"
    assert len(items[0]["matched_seeds"]) == 2
    assert items[0]["score"] > 0

    reasons = items[0]["reasons"]
    assert any("Alice" in reason for reason in reasons)
    assert any("中文字幕" in reason for reason in reasons)


@pytest.mark.django_db
def test_recommendations_endpoint_can_include_existing_resources(
    api_client, monkeypatch, resource_factory, actor_factory
):
    from nassav.source import Jable

    actor = actor_factory(name="Alice")
    seed_resource = resource_factory(avid="SEED-111", original_title="Seed")
    seed_resource.actors.add(actor)
    resource_factory(avid="REC-EXIST", original_title="Existing Recommended")

    monkeypatch.setattr(
        Jable,
        "search",
        lambda self, keyword, page=1: [
            {
                "avid": "REC-EXIST",
                "title": "Existing Result",
                "detail_url": "https://jable.tv/videos/rec-exist/",
                "cover_url": "https://assets-cdn.jable.tv/contents/videos_screenshots/0/11/320x180/1.jpg",
                "metrics": {"views": 100, "likes": 10},
            }
        ],
    )

    response = api_client.get(
        "/nassav/api/recommendations/",
        {
            "actor_seed_limit": 1,
            "genre_seed_limit": 1,
            "exclude_existing": "false",
        },
    )
    body = response.json()
    assert body["code"] == 200
    assert len(body["data"]["items"]) == 1
    assert body["data"]["items"][0]["avid"] == "REC-EXIST"
    assert body["data"]["meta"]["effective_request"]["exclude_existing"] is False


@pytest.mark.django_db
def test_recommendations_demo_endpoint_aliases_manager(
    api_client, monkeypatch, resource_factory, actor_factory
):
    from nassav.source import Jable

    actor = actor_factory(name="Alice")
    resource = resource_factory(avid="SEED-301", original_title="Seed Resource")
    resource.actors.add(actor)

    monkeypatch.setattr(
        Jable,
        "search",
        lambda self, keyword, page=1: [
            {
                "avid": "REC-301",
                "title": "Alias Result",
                "detail_url": "https://jable.tv/videos/rec-301/",
                "cover_url": "https://img/rec-301.jpg",
                "metrics": {"views": 10, "likes": 1},
            }
        ],
    )

    response = api_client.get(
        "/nassav/api/recommendations/demo",
        {"actor_seed_limit": 1, "genre_seed_limit": 1},
    )
    assert response.status_code == 200

    body = response.json()
    assert body["code"] == 200
    assert body["data"]["meta"]["recommender"] == "jable_search"
    assert body["data"]["meta"]["strategy"] == "local_preference"
    assert body["data"]["items"][0]["avid"] == "REC-301"


@pytest.mark.django_db
def test_recommendation_cover_endpoint_caches_file(api_client, monkeypatch, tmp_path):
    from django.conf import settings
    from nassav.source import Jable

    original_dir = settings.RECOMMENDATION_COVER_DIR
    settings.RECOMMENDATION_COVER_DIR = tmp_path

    def fake_download_file(self, url, save_path, referer=""):
        _ = self
        _ = url
        _ = referer
        with open(save_path, "wb") as f:
            f.write(b"fake-image")
        return True

    monkeypatch.setattr(Jable, "download_file", fake_download_file)

    try:
        response = api_client.get(
            "/nassav/api/recommendations/cover",
            {
                "url": "https://assets-cdn.jable.tv/contents/videos_screenshots/0/11/320x180/1.jpg"
            },
        )
        assert response.status_code == 200

        cached_files = list(tmp_path.iterdir())
        assert len(cached_files) == 1
        assert cached_files[0].suffix == ".jpg"
    finally:
        settings.RECOMMENDATION_COVER_DIR = original_dir


@pytest.mark.django_db
def test_recent_favorite_strategy_prefers_interacted_recent_seeds(
    api_client,
    monkeypatch,
    resource_factory,
    actor_factory,
):
    from nassav.source import Jable

    recent_actor = actor_factory(name="Recent Favorite Actor")
    legacy_actor = actor_factory(name="Legacy Actor")

    recent_resource = resource_factory(
        avid="RECENT-001",
        original_title="Recent Favorite",
        watched=True,
        is_favorite=True,
        created_at=timezone.now(),
    )
    recent_resource.actors.add(recent_actor)

    legacy_resource_1 = resource_factory(
        avid="LEGACY-001",
        original_title="Legacy 1",
        created_at=timezone.now() - timedelta(days=365),
    )
    legacy_resource_1.actors.add(legacy_actor)

    legacy_resource_2 = resource_factory(
        avid="LEGACY-002",
        original_title="Legacy 2",
        created_at=timezone.now() - timedelta(days=300),
    )
    legacy_resource_2.actors.add(legacy_actor)

    monkeypatch.setattr(Jable, "search", lambda self, keyword, page=1: [])

    response = api_client.get(
        "/nassav/api/recommendations/",
        {
            "strategy": "recent_favorite",
            "actor_seed_limit": 2,
            "genre_seed_limit": 1,
        },
    )
    body = response.json()
    assert body["code"] == 200

    actor_seeds = [
        seed for seed in body["data"]["seeds"] if seed["seed_type"] == "actor"
    ]
    assert len(actor_seeds) == 1
    assert actor_seeds[0]["value"] == "Recent Favorite Actor"
    assert actor_seeds[0]["source"] == "local_interacted_actor"
    assert actor_seeds[0]["preference_score"] > 0


@pytest.mark.django_db
def test_actor_heavy_strategy_prefers_actor_seed_matches_over_genre_only_matches(
    api_client,
    monkeypatch,
    resource_factory,
    actor_factory,
    genre_factory,
):
    from nassav.source import Jable

    actor = actor_factory(name="Alice")
    genre = genre_factory(name="中文字幕")

    actor_seed = resource_factory(avid="ACTOR-SEED-001", original_title="Actor Seed")
    actor_seed.actors.add(actor)

    genre_seed = resource_factory(avid="GENRE-SEED-001", original_title="Genre Seed")
    genre_seed.genres.add(genre)

    def fake_search(self, keyword, page=1):
        _ = self
        _ = page
        if keyword == "Alice":
            return [
                {
                    "avid": "REC-ACTOR",
                    "title": "Actor Match",
                    "detail_url": "https://jable.tv/videos/rec-actor/",
                    "cover_url": "https://img/rec-actor.jpg",
                    "metrics": {"views": 100, "likes": 10},
                }
            ]
        if keyword == "中文字幕":
            return [
                {
                    "avid": "REC-GENRE",
                    "title": "Genre Match",
                    "detail_url": "https://jable.tv/videos/rec-genre/",
                    "cover_url": "https://img/rec-genre.jpg",
                    "metrics": {"views": 100, "likes": 10},
                }
            ]
        return []

    monkeypatch.setattr(Jable, "search", fake_search)

    response = api_client.get(
        "/nassav/api/recommendations/",
        {
            "strategy": "actor_heavy",
            "actor_seed_limit": 1,
            "genre_seed_limit": 1,
        },
    )
    body = response.json()
    assert body["code"] == 200
    assert [item["avid"] for item in body["data"]["items"]] == [
        "REC-ACTOR",
        "REC-GENRE",
    ]


@pytest.mark.django_db
def test_recommendations_endpoint_persists_snapshot_and_items(
    api_client, monkeypatch, resource_factory, actor_factory
):
    from nassav.models import RecommendationItem, RecommendationSnapshot
    from nassav.source import Jable

    actor = actor_factory(name="Alice")
    seed_resource = resource_factory(avid="SEED-401", original_title="Seed")
    seed_resource.actors.add(actor)

    monkeypatch.setattr(
        Jable,
        "search",
        lambda self, keyword, page=1: [
            {
                "avid": "REC-401",
                "title": "Persisted Result",
                "detail_url": "https://jable.tv/videos/rec-401/",
                "cover_url": "https://img/rec-401.jpg",
                "metrics": {"views": 100, "likes": 10},
            }
        ],
    )

    response = api_client.get(
        "/nassav/api/recommendations/",
        {"actor_seed_limit": 1, "genre_seed_limit": 1},
    )
    assert response.status_code == 200

    snapshot = RecommendationSnapshot.objects.get()
    item = RecommendationItem.objects.get(snapshot=snapshot)
    body = response.json()
    assert snapshot.recommender_id == "jable_search"
    assert snapshot.strategy_id == "local_preference"
    assert snapshot.request_fingerprint == body["data"]["meta"]["request_fingerprint"]
    assert snapshot.item_count == 1
    assert item.avid == "REC-401"
    assert item.rank == 1
    assert item.reasons


@pytest.mark.django_db
def test_recommendations_endpoint_avoids_recent_snapshot_items_on_repeat_request(
    api_client, monkeypatch, resource_factory, actor_factory
):
    from nassav.models import RecommendationSnapshot
    from nassav.source import Jable

    actor = actor_factory(name="Alice")
    seed_resource = resource_factory(avid="SEED-501", original_title="Seed")
    seed_resource.actors.add(actor)

    monkeypatch.setattr(
        Jable,
        "search",
        lambda self, keyword, page=1: [
            {
                "avid": "REC-501-A",
                "title": "First Result",
                "detail_url": "https://jable.tv/videos/rec-501-a/",
                "cover_url": "https://img/rec-501-a.jpg",
                "metrics": {"views": 1000, "likes": 200},
            },
            {
                "avid": "REC-501-B",
                "title": "Second Result",
                "detail_url": "https://jable.tv/videos/rec-501-b/",
                "cover_url": "https://img/rec-501-b.jpg",
                "metrics": {"views": 900, "likes": 180},
            },
        ],
    )

    first_response = api_client.get(
        "/nassav/api/recommendations/",
        {
            "actor_seed_limit": 1,
            "genre_seed_limit": 1,
            "limit": 1,
        },
    )
    second_response = api_client.get(
        "/nassav/api/recommendations/",
        {
            "actor_seed_limit": 1,
            "genre_seed_limit": 1,
            "limit": 1,
        },
    )

    first_item = first_response.json()["data"]["items"][0]
    second_body = second_response.json()
    second_item = second_body["data"]["items"][0]
    assert first_item["avid"] == "REC-501-A"
    assert second_item["avid"] == "REC-501-B"
    assert second_body["data"]["meta"]["history_context"]["filtered_history_count"] >= 1
    assert RecommendationSnapshot.objects.count() == 2
