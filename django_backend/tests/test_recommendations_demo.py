import pytest


@pytest.fixture(autouse=True)
def stub_recommendation_discovery(monkeypatch):
    from nassav.source import Jable

    monkeypatch.setattr(
        Jable,
        "discover_hot_items",
        lambda self, page=1, force_refresh=False: [],
    )
    monkeypatch.setattr(
        Jable,
        "discover_latest_updates",
        lambda self, page=1, force_refresh=False: [],
    )


@pytest.mark.django_db
def test_recommendations_options_endpoint(api_client):
    response = api_client.get("/nassav/api/recommendations/options")
    assert response.status_code == 200

    body = response.json()
    assert body["code"] == 200
    assert body["data"]["defaults"]["recommender"] == "jable_page_lookup"
    assert body["data"]["defaults"]["strategy"] == "local_preference"
    assert [item["id"] for item in body["data"]["recommenders"]] == [
        "jable_page_lookup"
    ]
    assert any(item["id"] == "local_preference" for item in body["data"]["strategies"])
    assert len(body["data"]["strategies"]) == 1
    local_preference = next(
        item for item in body["data"]["strategies"] if item["id"] == "local_preference"
    )
    assert local_preference["default_request_overrides"]["limit"] == 12
    assert isinstance(local_preference["parameter_profile"], list)
    assert any(
        section["title"] == "基础参数"
        for section in local_preference["parameter_profile"]
    )


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

    monkeypatch.setattr(
        Jable,
        "search",
        lambda self, keyword, page=1, force_refresh=False: [],
    )

    response = api_client.get("/nassav/api/recommendations/")
    assert response.status_code == 200

    body = response.json()
    assert body["code"] == 200
    assert body["data"]["meta"]["recommender"] == "jable_page_lookup"
    assert body["data"]["meta"]["strategy"] == "local_preference"
    assert body["data"]["meta"]["snapshot_id"] is not None
    assert body["data"]["meta"]["request_fingerprint"]
    assert body["data"]["meta"]["recommender_detail"]["name"] == "Jable Page Lookup"
    assert "page lookup" in body["data"]["meta"]["strategy_detail"]["description"]
    assert body["data"]["meta"]["effective_request"]["limit"] == 12
    assert body["data"]["meta"]["effective_request"]["exclude_existing"] is True
    assert (
        body["data"]["meta"]["effective_request"]["avoid_recent_recommendations"]
        is True
    )
    assert (
        body["data"]["meta"]["history_context"]["recent_history_candidate_count"] == 0
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

    def fake_search(self, keyword, page=1, force_refresh=False):
        _ = self
        _ = page
        _ = force_refresh
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
        lambda self, keyword, page=1, force_refresh=False: [
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
        lambda self, keyword, page=1, force_refresh=False: [
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
    assert body["data"]["meta"]["recommender"] == "jable_page_lookup"
    assert body["data"]["meta"]["strategy"] == "local_preference"
    assert body["data"]["items"][0]["avid"] == "REC-301"


@pytest.mark.django_db
def test_recommendations_endpoint_accepts_force_refresh_external(
    api_client, monkeypatch, resource_factory, actor_factory
):
    from nassav.source import Jable

    actor = actor_factory(name="Alice")
    seed_resource = resource_factory(avid="SEED-401", original_title="Seed")
    seed_resource.actors.add(actor)

    monkeypatch.setattr(
        Jable,
        "search",
        lambda self, keyword, page=1, force_refresh=False: [],
    )

    response = api_client.get(
        "/nassav/api/recommendations/",
        {"force_refresh_external": "true"},
    )
    assert response.status_code == 200

    body = response.json()
    assert body["code"] == 200
    assert body["data"]["meta"]["effective_request"]["force_refresh_external"] is True


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
def test_type_preference_controls_actor_vs_genre_weight(
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
            "actor_seed_limit": 1,
            "genre_seed_limit": 1,
            "type_preference": "actor_heavy",
        },
    )
    body = response.json()
    assert body["code"] == 200
    assert body["data"]["items"][0]["avid"] == "REC-ACTOR"

    genre_heavy_response = api_client.get(
        "/nassav/api/recommendations/",
        {
            "actor_seed_limit": 1,
            "genre_seed_limit": 1,
            "type_preference": "genre_heavy",
            "avoid_recent_recommendations": "false",
        },
    )
    genre_heavy_body = genre_heavy_response.json()
    assert genre_heavy_body["code"] == 200
    assert genre_heavy_body["data"]["items"][0]["avid"] == "REC-GENRE"


@pytest.mark.django_db
def test_rare_actor_preference_includes_mid_and_low_frequency_actor_seeds(
    api_client, monkeypatch, resource_factory, actor_factory
):
    from nassav.source import Jable

    actors = [actor_factory(name=f"Actor-{index:02d}") for index in range(1, 10)]
    for index, actor in enumerate(actors, start=1):
        resource_count = 10 - index
        for replica in range(resource_count):
            resource = resource_factory(
                avid=f"SEED-RARE-{index:02d}-{replica:02d}",
                original_title=f"Seed {index}-{replica}",
            )
            resource.actors.add(actor)

    monkeypatch.setattr(Jable, "search", lambda self, keyword, page=1: [])

    response = api_client.get(
        "/nassav/api/recommendations/",
        {
            "actor_seed_limit": 5,
            "genre_seed_limit": 0,
            "actor_preference": "rare",
        },
    )
    body = response.json()
    assert body["code"] == 200
    actor_seeds = [
        seed["value"]
        for seed in body["data"]["seeds"]
        if seed["seed_type"] == "actor"
        and seed["source"] in {"local_top_actor", "local_interacted_actor"}
    ]
    assert len(actor_seeds) == 5
    assert any(value in {"Actor-07", "Actor-08", "Actor-09"} for value in actor_seeds)
    assert any(value in {"Actor-04", "Actor-05", "Actor-06"} for value in actor_seeds)


@pytest.mark.django_db
def test_recommendations_endpoint_persists_snapshot_and_items(
    api_client, monkeypatch, resource_factory, actor_factory
):
    from nassav.models import (
        RecommendationItem,
        RecommendationItemSeed,
        RecommendationSeedProfile,
        RecommendationSnapshot,
    )
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
    assert snapshot.recommender_id == "jable_page_lookup"
    assert snapshot.strategy_id == "local_preference"
    assert snapshot.request_fingerprint == body["data"]["meta"]["request_fingerprint"]
    assert snapshot.item_count == 1
    assert item.avid == "REC-401"
    assert item.rank == 1
    assert item.reasons
    item_seed = RecommendationItemSeed.objects.get(item=item)
    assert item_seed.seed_type == "actor"
    assert item_seed.seed_value == "Alice"
    profile = RecommendationSeedProfile.objects.get(
        seed_type="actor",
        normalized_value="alice",
    )
    assert profile.recommended_count >= 1


@pytest.mark.django_db
def test_blocked_seed_profile_excludes_matching_seed_from_recommendation_pool(
    api_client, monkeypatch, resource_factory, actor_factory
):
    from nassav.models import RecommendationSeedProfile
    from nassav.source import Jable

    actor = actor_factory(name="Alice")
    seed_resource = resource_factory(avid="SEED-BLOCK-001", original_title="Seed")
    seed_resource.actors.add(actor)

    RecommendationSeedProfile.objects.create(
        seed_type="actor",
        value="Alice",
        normalized_value="alice",
        is_blocked=True,
        block_reason="manual",
    )

    monkeypatch.setattr(
        Jable,
        "search",
        lambda self, keyword, page=1: [
            {
                "avid": "REC-BLOCK-001",
                "title": "Blocked Seed Result",
                "detail_url": "https://jable.tv/videos/rec-block-001/",
                "cover_url": "https://img/rec-block-001.jpg",
                "metrics": {"views": 100, "likes": 10},
            }
        ],
    )

    response = api_client.get(
        "/nassav/api/recommendations/",
        {"actor_seed_limit": 1, "genre_seed_limit": 0},
    )
    body = response.json()
    assert body["code"] == 200
    assert body["data"]["items"] == []
    assert all(seed["value"] != "Alice" for seed in body["data"]["seeds"])


@pytest.mark.django_db
def test_recommendation_seed_block_endpoint_blocks_and_unblocks_actor(
    api_client, actor_factory
):
    actor = actor_factory(name="Alice")

    block_response = api_client.post(
        "/nassav/api/recommendations/seed-block",
        {"seed_type": "actor", "id": actor.id, "reason": "manual"},
        format="json",
    )
    assert block_response.status_code == 200
    block_body = block_response.json()
    assert block_body["code"] == 200
    assert block_body["data"]["is_blocked"] is True

    list_response = api_client.get("/nassav/api/actors/", {"id": actor.id})
    list_body = list_response.json()
    assert list_body["code"] == 200
    assert list_body["data"][0]["is_blocked"] is True

    unblock_response = api_client.delete(
        "/nassav/api/recommendations/seed-block",
        {"seed_type": "actor", "id": actor.id},
        format="json",
    )
    assert unblock_response.status_code == 200
    unblock_body = unblock_response.json()
    assert unblock_body["data"]["is_blocked"] is False

    refreshed_list_response = api_client.get("/nassav/api/actors/", {"id": actor.id})
    refreshed_list_body = refreshed_list_response.json()
    assert refreshed_list_body["data"][0]["is_blocked"] is False


@pytest.mark.django_db
def test_recommendation_seed_block_endpoint_blocks_genre(api_client, genre_factory):
    genre = genre_factory(name="中文字幕")

    response = api_client.post(
        "/nassav/api/recommendations/seed-block",
        {"seed_type": "genre", "id": genre.id, "reason": "manual"},
        format="json",
    )
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert body["data"]["is_blocked"] is True

    list_response = api_client.get("/nassav/api/genres/", {"id": genre.id})
    list_body = list_response.json()
    assert list_body["code"] == 200
    assert list_body["data"][0]["is_blocked"] is True


@pytest.mark.django_db
def test_recommendation_avid_blocklist_endpoint_lists_adds_and_removes(
    api_client, resource_factory
):
    resource = resource_factory(
        avid="ABC-123",
        original_title="Blocked Resource",
        source="Jable",
    )

    create_response = api_client.post(
        "/nassav/api/recommendations/avid-blocklist",
        {"avid": resource.avid, "reason": "manual"},
        format="json",
    )
    assert create_response.status_code == 200
    create_body = create_response.json()
    assert create_body["code"] == 200
    assert create_body["data"]["avid"] == "ABC-123"
    assert create_body["data"]["is_blocked"] is True

    list_response = api_client.get(
        "/nassav/api/recommendations/avid-blocklist",
        {"search": "ABC"},
    )
    assert list_response.status_code == 200
    list_body = list_response.json()
    assert list_body["code"] == 200
    assert list_body["data"][0]["avid"] == "ABC-123"
    assert list_body["data"][0]["title"] == "Blocked Resource"
    assert list_body["data"][0]["exists_in_library"] is True

    delete_response = api_client.delete(
        "/nassav/api/recommendations/avid-blocklist",
        {"avid": resource.avid},
        format="json",
    )
    assert delete_response.status_code == 200
    delete_body = delete_response.json()
    assert delete_body["data"]["avid"] == "ABC-123"
    assert delete_body["data"]["is_blocked"] is False


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


@pytest.mark.django_db
def test_recommendations_endpoint_penalizes_cross_strategy_recent_results(
    api_client, monkeypatch, resource_factory, actor_factory
):
    from nassav.source import Jable

    actor = actor_factory(name="Alice")
    seed_resource = resource_factory(avid="SEED-601", original_title="Seed")
    seed_resource.actors.add(actor)

    monkeypatch.setattr(
        Jable,
        "search",
        lambda self, keyword, page=1: [
            {
                "avid": "REC-601-A",
                "title": "Frequent Result",
                "detail_url": "https://jable.tv/videos/rec-601-a/",
                "cover_url": "https://img/rec-601-a.jpg",
                "metrics": {"views": 2200, "likes": 260},
            },
            {
                "avid": "REC-601-B",
                "title": "Novel Result",
                "detail_url": "https://jable.tv/videos/rec-601-b/",
                "cover_url": "https://img/rec-601-b.jpg",
                "metrics": {"views": 2000, "likes": 250},
            },
        ],
    )

    first_response = api_client.get(
        "/nassav/api/recommendations/",
        {
            "strategy": "local_preference",
            "limit": 1,
            "actor_seed_limit": 1,
            "genre_seed_limit": 1,
            "avoid_recent_recommendations": "false",
        },
    )
    second_response = api_client.get(
        "/nassav/api/recommendations/",
        {
            "limit": 1,
            "actor_seed_limit": 1,
            "genre_seed_limit": 1,
            "avoid_recent_recommendations": "false",
            "type_preference": "genre_heavy",
        },
    )

    assert first_response.json()["data"]["items"][0]["avid"] == "REC-601-A"
    second_body = second_response.json()
    assert second_body["data"]["items"][0]["avid"] == "REC-601-B"
    assert (
        second_body["data"]["meta"]["history_context"]["recent_history_candidate_count"]
        >= 1
    )
    novelty_breakdowns = [
        item
        for item in second_body["data"]["items"][0]["score_breakdown"]
        if item["factor"] == "NoveltyFactor"
    ]
    assert novelty_breakdowns


@pytest.mark.django_db
def test_recommendation_feedback_endpoint_accepts_only_dislike(
    api_client, monkeypatch, resource_factory, actor_factory
):
    from nassav.source import Jable

    actor = actor_factory(name="Alice")
    seed_resource = resource_factory(avid="SEED-701", original_title="Seed")
    seed_resource.actors.add(actor)

    monkeypatch.setattr(
        Jable,
        "search",
        lambda self, keyword, page=1: [
            {
                "avid": "REC-701-A",
                "title": "Base Winner",
                "detail_url": "https://jable.tv/videos/rec-701-a/",
                "cover_url": "https://img/rec-701-a.jpg",
                "metrics": {"views": 3200, "likes": 350},
            },
            {
                "avid": "REC-701-B",
                "title": "Feedback Winner",
                "detail_url": "https://jable.tv/videos/rec-701-b/",
                "cover_url": "https://img/rec-701-b.jpg",
                "metrics": {"views": 2800, "likes": 300},
            },
        ],
    )

    first_response = api_client.get(
        "/nassav/api/recommendations/",
        {
            "limit": 2,
            "actor_seed_limit": 1,
            "genre_seed_limit": 1,
            "avoid_recent_recommendations": "false",
        },
    )
    first_body = first_response.json()
    assert [item["avid"] for item in first_body["data"]["items"]] == [
        "REC-701-A",
        "REC-701-B",
    ]

    invalid_feedback_response = api_client.post(
        "/nassav/api/recommendations/feedback",
        {
            "snapshot_id": first_body["data"]["items"][0]["snapshot_id"],
            "avid": "REC-701-A",
            "feedback": "clear",
        },
        format="json",
    )
    assert invalid_feedback_response.status_code == 400
    assert invalid_feedback_response.json()["code"] == 400

    dislike_response = api_client.post(
        "/nassav/api/recommendations/feedback",
        {
            "snapshot_id": first_body["data"]["items"][0]["snapshot_id"],
            "avid": "REC-701-A",
            "feedback": "dislike",
        },
        format="json",
    )
    assert dislike_response.status_code == 200
    assert dislike_response.json()["data"]["feedback"] == "dislike"


@pytest.mark.django_db
def test_recommendation_dislike_feedback_blocks_same_avid_from_future_results(
    api_client, monkeypatch, resource_factory, actor_factory
):
    from nassav.models import (
        RecommendationAvidBlocklist,
        RecommendationFeedback,
        RecommendationSeedProfile,
    )
    from nassav.source import Jable

    actor = actor_factory(name="Alice")
    seed_resource = resource_factory(avid="SEED-702", original_title="Seed")
    seed_resource.actors.add(actor)

    monkeypatch.setattr(
        Jable,
        "search",
        lambda self, keyword, page=1: [
            {
                "avid": "REC-702-A",
                "title": "Disliked Candidate",
                "detail_url": "https://jable.tv/videos/rec-702-a/",
                "cover_url": "https://img/rec-702-a.jpg",
                "metrics": {"views": 3600, "likes": 420},
            },
            {
                "avid": "REC-702-B",
                "title": "Fallback Candidate",
                "detail_url": "https://jable.tv/videos/rec-702-b/",
                "cover_url": "https://img/rec-702-b.jpg",
                "metrics": {"views": 2800, "likes": 300},
            },
            {
                "avid": "REC-702-C",
                "title": "Third Candidate",
                "detail_url": "https://jable.tv/videos/rec-702-c/",
                "cover_url": "https://img/rec-702-c.jpg",
                "metrics": {"views": 2400, "likes": 260},
            },
        ],
    )

    first_response = api_client.get(
        "/nassav/api/recommendations/",
        {
            "limit": 3,
            "actor_seed_limit": 1,
            "genre_seed_limit": 1,
            "avoid_recent_recommendations": "false",
        },
    )
    first_body = first_response.json()
    assert [item["avid"] for item in first_body["data"]["items"]] == [
        "REC-702-A",
        "REC-702-B",
        "REC-702-C",
    ]

    feedback_response = api_client.post(
        "/nassav/api/recommendations/feedback",
        {
            "snapshot_id": first_body["data"]["items"][0]["snapshot_id"],
            "avid": "REC-702-A",
            "feedback": "dislike",
        },
        format="json",
    )
    assert feedback_response.status_code == 200
    assert RecommendationFeedback.objects.count() == 1
    assert RecommendationAvidBlocklist.objects.filter(avid="REC-702-A").exists()
    assert (
        RecommendationSeedProfile.objects.get(
            seed_type="actor",
            normalized_value="alice",
        ).disliked_count
        >= 1
    )

    second_response = api_client.get(
        "/nassav/api/recommendations/",
        {
            "limit": 3,
            "actor_seed_limit": 1,
            "genre_seed_limit": 1,
            "avoid_recent_recommendations": "false",
        },
    )
    second_body = second_response.json()
    second_avids = [item["avid"] for item in second_body["data"]["items"]]
    assert "REC-702-A" not in second_avids
    assert set(second_avids) == {"REC-702-B", "REC-702-C"}


@pytest.mark.django_db
def test_recommendation_reset_endpoint_clears_snapshots_and_feedback(
    api_client, monkeypatch, resource_factory, actor_factory
):
    from nassav.models import (
        RecommendationAvidBlocklist,
        RecommendationFeedback,
        RecommendationItem,
        RecommendationItemSeed,
        RecommendationSeedProfile,
        RecommendationSnapshot,
    )
    from nassav.source import Jable

    actor = actor_factory(name="Alice")
    seed_resource = resource_factory(avid="SEED-703", original_title="Seed")
    seed_resource.actors.add(actor)

    monkeypatch.setattr(
        Jable,
        "search",
        lambda self, keyword, page=1: [
            {
                "avid": "REC-703-A",
                "title": "Candidate",
                "detail_url": "https://jable.tv/videos/rec-703-a/",
                "cover_url": "https://img/rec-703-a.jpg",
                "metrics": {"views": 3200, "likes": 260},
            }
        ],
    )

    first_response = api_client.get("/nassav/api/recommendations/", {"limit": 1})
    snapshot_id = first_response.json()["data"]["items"][0]["snapshot_id"]
    feedback_response = api_client.post(
        "/nassav/api/recommendations/feedback",
        {"snapshot_id": snapshot_id, "avid": "REC-703-A", "feedback": "dislike"},
        format="json",
    )
    assert feedback_response.status_code == 200
    assert RecommendationSnapshot.objects.count() == 1
    assert RecommendationItem.objects.count() == 1
    assert RecommendationItemSeed.objects.count() == 1
    assert RecommendationFeedback.objects.count() == 1
    assert RecommendationAvidBlocklist.objects.count() == 1
    assert RecommendationSeedProfile.objects.count() >= 1

    reset_response = api_client.post(
        "/nassav/api/recommendations/reset", {}, format="json"
    )
    reset_body = reset_response.json()
    assert reset_response.status_code == 200
    assert reset_body["code"] == 200
    assert reset_body["data"]["snapshot_count"] == 1
    assert reset_body["data"]["item_count"] == 1
    assert reset_body["data"]["item_seed_count"] == 1
    assert reset_body["data"]["feedback_count"] == 1
    assert reset_body["data"]["blocklist_count"] == 1
    assert reset_body["data"]["seed_profile_count"] >= 1
    assert RecommendationSnapshot.objects.count() == 0
    assert RecommendationItem.objects.count() == 0
    assert RecommendationItemSeed.objects.count() == 0
    assert RecommendationFeedback.objects.count() == 0
    assert RecommendationAvidBlocklist.objects.count() == 0
    assert RecommendationSeedProfile.objects.count() == 0


@pytest.mark.django_db
def test_recommendations_endpoint_tops_up_when_recent_filter_would_underfill(
    api_client, monkeypatch, resource_factory, actor_factory
):
    from nassav.source import Jable

    actor = actor_factory(name="Alice")
    seed_resource = resource_factory(avid="SEED-901", original_title="Seed")
    seed_resource.actors.add(actor)

    monkeypatch.setattr(
        Jable,
        "search",
        lambda self, keyword, page=1: [
            {
                "avid": "REC-901-A",
                "title": "Result A",
                "detail_url": "https://jable.tv/videos/rec-901-a/",
                "cover_url": "https://img/rec-901-a.jpg",
                "metrics": {"views": 1800, "likes": 120},
            },
            {
                "avid": "REC-901-B",
                "title": "Result B",
                "detail_url": "https://jable.tv/videos/rec-901-b/",
                "cover_url": "https://img/rec-901-b.jpg",
                "metrics": {"views": 1700, "likes": 110},
            },
            {
                "avid": "REC-901-C",
                "title": "Result C",
                "detail_url": "https://jable.tv/videos/rec-901-c/",
                "cover_url": "https://img/rec-901-c.jpg",
                "metrics": {"views": 900, "likes": 70},
            },
        ],
    )

    first_response = api_client.get(
        "/nassav/api/recommendations/",
        {
            "limit": 2,
            "actor_seed_limit": 1,
            "genre_seed_limit": 1,
        },
    )
    second_response = api_client.get(
        "/nassav/api/recommendations/",
        {
            "limit": 2,
            "actor_seed_limit": 1,
            "genre_seed_limit": 1,
        },
    )

    first_items = first_response.json()["data"]["items"]
    second_items = second_response.json()["data"]["items"]

    assert len(first_items) == 2
    assert len(second_items) == 2
    assert "REC-901-C" in [item["avid"] for item in second_items]


@pytest.mark.django_db
def test_recommendations_endpoint_uses_actor_aliases_for_seed_recall(
    api_client, monkeypatch, resource_factory, actor_factory
):
    from nassav.source import Jable

    actor = actor_factory(name="めぐり（藤浦めぐ）")
    seed_resource = resource_factory(avid="SEED-902", original_title="Seed")
    seed_resource.actors.add(actor)

    captured_keywords = []

    def fake_search(self, keyword, page=1):
        _ = self
        _ = page
        captured_keywords.append(keyword)
        if keyword == "藤浦めぐ":
            return [
                {
                    "avid": "REC-902-A",
                    "title": "Alias Hit",
                    "detail_url": "https://jable.tv/videos/rec-902-a/",
                    "cover_url": "https://img/rec-902-a.jpg",
                    "metrics": {"views": 1500, "likes": 180},
                }
            ]
        return []

    monkeypatch.setattr(Jable, "search", fake_search)

    response = api_client.get(
        "/nassav/api/recommendations/",
        {
            "limit": 1,
            "actor_seed_limit": 1,
            "genre_seed_limit": 1,
        },
    )

    body = response.json()
    assert body["code"] == 200
    assert body["data"]["items"][0]["avid"] == "REC-902-A"
    assert "めぐり（藤浦めぐ）" in captured_keywords
    assert "藤浦めぐ" in captured_keywords


@pytest.mark.django_db
def test_recommendations_endpoint_uses_actor_source_mapping_for_model_recall(
    api_client, monkeypatch, resource_factory, actor_factory
):
    from nassav.models import ActorSourceMapping
    from nassav.source import Jable

    actor = actor_factory(name="明里つむぎ")
    seed_resource = resource_factory(avid="SEED-902-MAP", original_title="Seed")
    seed_resource.actors.add(actor)
    ActorSourceMapping.objects.create(
        actor=actor,
        source_name="jable",
        source_actor_name="明里つむぎ",
        source_actor_slug="tsumugi-akari",
        aliases=["Tsumugi Akari"],
        is_verified=True,
    )

    captured_model_slugs = []
    captured_keywords = []

    monkeypatch.setattr(
        Jable,
        "get_model_videos",
        lambda self, model_slug, page=1, sort_by="video_viewed": (
            captured_model_slugs.append((model_slug, page, sort_by))
            or [
                {
                    "avid": "REC-902-MAP",
                    "title": "Mapped Model Hit",
                    "detail_url": "https://jable.tv/videos/rec-902-map/",
                    "cover_url": "https://img/rec-902-map.jpg",
                    "metrics": {"views": 2600, "likes": 240},
                }
            ]
        ),
    )
    monkeypatch.setattr(
        Jable,
        "search",
        lambda self, keyword, page=1: captured_keywords.append(keyword) or [],
    )

    response = api_client.get(
        "/nassav/api/recommendations/",
        {
            "limit": 1,
            "actor_seed_limit": 1,
            "genre_seed_limit": 1,
        },
    )

    body = response.json()
    assert body["code"] == 200
    assert body["data"]["items"][0]["avid"] == "REC-902-MAP"
    assert captured_model_slugs == [("tsumugi-akari", 1, "video_viewed")]
    assert captured_keywords == []


@pytest.mark.django_db
def test_recommendations_endpoint_does_not_write_actor_mapping(
    api_client, monkeypatch, resource_factory, actor_factory
):
    actor = actor_factory(name="めぐり（藤浦めぐ）")
    seed_resource = resource_factory(avid="SEED-LAZY-404", original_title="Seed")
    seed_resource.actors.add(actor)

    from nassav.models import ActorSourceMapping
    from nassav.source import Jable

    monkeypatch.setattr(
        Jable,
        "search",
        lambda self, keyword, page=1: [
            {
                "avid": "REC-LAZY-404",
                "title": "Lazy Mapping 404",
                "detail_url": "https://jable.tv/videos/rec-lazy-404/",
                "cover_url": "https://img/rec-lazy-404.jpg",
                "metrics": {"views": 100, "likes": 10},
            }
        ],
    )

    response = api_client.get(
        "/nassav/api/recommendations/",
        {"limit": 1, "actor_seed_limit": 1, "genre_seed_limit": 0},
    )

    body = response.json()
    assert response.status_code == 200
    assert body["code"] == 200
    assert body["data"]["items"][0]["avid"] == "REC-LAZY-404"
    assert not ActorSourceMapping.objects.filter(
        actor=actor,
        source_name="jable",
    ).exists()


@pytest.mark.django_db
def test_recommendations_endpoint_expands_to_lower_ranked_seeds_when_exhausted(
    api_client, monkeypatch, resource_factory, actor_factory
):
    from nassav.source import Jable

    alice = actor_factory(name="Alice")
    bob = actor_factory(name="Bob")
    carol = actor_factory(name="Carol")

    for index in range(3):
        resource_factory(avid=f"ALICE-SEED-{index}", original_title="Seed").actors.add(
            alice
        )
    for index in range(2):
        resource_factory(avid=f"BOB-SEED-{index}", original_title="Seed").actors.add(
            bob
        )
    resource_factory(avid="CAROL-SEED-0", original_title="Seed").actors.add(carol)

    def fake_search(self, keyword, page=1):
        _ = self
        _ = page
        mapping = {
            "Alice": [
                {
                    "avid": "REC-LATE-A",
                    "title": "Alice Candidate",
                    "detail_url": "https://jable.tv/videos/rec-late-a/",
                    "cover_url": "https://img/rec-late-a.jpg",
                    "metrics": {"views": 2400, "likes": 220},
                }
            ],
            "Bob": [
                {
                    "avid": "REC-LATE-B",
                    "title": "Bob Candidate",
                    "detail_url": "https://jable.tv/videos/rec-late-b/",
                    "cover_url": "https://img/rec-late-b.jpg",
                    "metrics": {"views": 2200, "likes": 210},
                }
            ],
            "Carol": [
                {
                    "avid": "REC-LATE-C",
                    "title": "Carol Candidate",
                    "detail_url": "https://jable.tv/videos/rec-late-c/",
                    "cover_url": "https://img/rec-late-c.jpg",
                    "metrics": {"views": 1800, "likes": 190},
                }
            ],
        }
        return mapping.get(keyword, [])

    monkeypatch.setattr(Jable, "search", fake_search)

    first_response = api_client.get(
        "/nassav/api/recommendations/",
        {
            "limit": 2,
            "actor_seed_limit": 2,
            "genre_seed_limit": 1,
        },
    )
    second_response = api_client.get(
        "/nassav/api/recommendations/",
        {
            "limit": 3,
            "actor_seed_limit": 2,
            "genre_seed_limit": 1,
        },
    )

    assert len(first_response.json()["data"]["items"]) == 2
    second_items = second_response.json()["data"]["items"]
    assert len(second_items) == 3
    assert "REC-LATE-C" in [item["avid"] for item in second_items]
    assert any(
        seed["value"] == "Carol" for seed in second_response.json()["data"]["seeds"]
    )


@pytest.mark.django_db
def test_recommendations_endpoint_expands_when_primary_pool_is_only_recent(
    api_client, monkeypatch, resource_factory, actor_factory
):
    from nassav.source import Jable

    alice = actor_factory(name="Alice")
    bob = actor_factory(name="Bob")
    carol = actor_factory(name="Carol")

    for index in range(3):
        resource_factory(
            avid=f"RECENT-ALICE-SEED-{index}",
            original_title="Seed",
        ).actors.add(alice)
    for index in range(2):
        resource_factory(
            avid=f"RECENT-BOB-SEED-{index}",
            original_title="Seed",
        ).actors.add(bob)
    resource_factory(avid="RECENT-CAROL-SEED-0", original_title="Seed").actors.add(
        carol
    )

    def fake_search(self, keyword, page=1):
        _ = self
        _ = page
        mapping = {
            "Alice": [
                {
                    "avid": "REC-POOL-A",
                    "title": "Alice Candidate A",
                    "detail_url": "https://jable.tv/videos/rec-pool-a/",
                    "cover_url": "https://img/rec-pool-a.jpg",
                    "metrics": {"views": 2600, "likes": 260},
                },
                {
                    "avid": "REC-POOL-B",
                    "title": "Alice Candidate B",
                    "detail_url": "https://jable.tv/videos/rec-pool-b/",
                    "cover_url": "https://img/rec-pool-b.jpg",
                    "metrics": {"views": 2400, "likes": 240},
                },
            ],
            "Bob": [
                {
                    "avid": "REC-POOL-C",
                    "title": "Bob Candidate",
                    "detail_url": "https://jable.tv/videos/rec-pool-c/",
                    "cover_url": "https://img/rec-pool-c.jpg",
                    "metrics": {"views": 2300, "likes": 230},
                }
            ],
            "Carol": [
                {
                    "avid": "REC-POOL-D",
                    "title": "Carol Candidate",
                    "detail_url": "https://jable.tv/videos/rec-pool-d/",
                    "cover_url": "https://img/rec-pool-d.jpg",
                    "metrics": {"views": 2100, "likes": 220},
                }
            ],
        }
        return mapping.get(keyword, [])

    monkeypatch.setattr(Jable, "search", fake_search)

    first_response = api_client.get(
        "/nassav/api/recommendations/",
        {
            "limit": 3,
            "actor_seed_limit": 2,
            "genre_seed_limit": 1,
        },
    )
    second_response = api_client.get(
        "/nassav/api/recommendations/",
        {
            "limit": 3,
            "actor_seed_limit": 2,
            "genre_seed_limit": 1,
        },
    )

    assert len(first_response.json()["data"]["items"]) == 3
    second_body = second_response.json()
    second_items = second_body["data"]["items"]
    assert len(second_items) == 3
    assert "REC-POOL-D" in [item["avid"] for item in second_items]
    assert any(seed["value"] == "Carol" for seed in second_body["data"]["seeds"])


@pytest.mark.django_db
def test_recommendations_endpoint_includes_hot_and_latest_discovery_candidates(
    api_client, monkeypatch, resource_factory, actor_factory
):
    from nassav.source import Jable

    actor = actor_factory(name="Alice")
    seed_resource = resource_factory(avid="SEED-903", original_title="Seed")
    seed_resource.actors.add(actor)

    monkeypatch.setattr(Jable, "search", lambda self, keyword, page=1: [])
    monkeypatch.setattr(
        Jable,
        "discover_hot_items",
        lambda self, page=1: [
            {
                "avid": "REC-903-HOT",
                "title": "Hot Candidate",
                "detail_url": "https://jable.tv/videos/rec-903-hot/",
                "cover_url": "https://img/rec-903-hot.jpg",
                "metrics": {
                    "views": 5000,
                    "likes": 500,
                    "discovery_sources": ["hot_board"],
                },
            }
        ],
    )
    monkeypatch.setattr(
        Jable,
        "discover_latest_updates",
        lambda self, page=1: [
            {
                "avid": "REC-903-NEW",
                "title": "Latest Candidate",
                "detail_url": "https://jable.tv/videos/rec-903-new/",
                "cover_url": "https://img/rec-903-new.jpg",
                "metrics": {
                    "views": 3200,
                    "likes": 240,
                    "discovery_sources": ["latest_updates"],
                },
            }
        ],
    )

    response = api_client.get(
        "/nassav/api/recommendations/",
        {
            "limit": 2,
            "actor_seed_limit": 1,
            "genre_seed_limit": 1,
        },
    )

    body = response.json()
    av_ids = [item["avid"] for item in body["data"]["items"]]
    assert "REC-903-HOT" in av_ids
    assert "REC-903-NEW" in av_ids
    assert any(
        entry["factor"] == "DiscoverySourceFactor"
        for item in body["data"]["items"]
        for entry in item["score_breakdown"]
    )


@pytest.mark.django_db
def test_feedback_learning_profile_builds_dislike_blacklist_and_seed_penalty(
    api_client, monkeypatch, resource_factory, actor_factory
):
    from nassav.recommendation.feedback import recommendation_feedback_repository
    from nassav.source import Jable

    actor = actor_factory(name="Alice")
    seed_resource = resource_factory(avid="SEED-905", original_title="Seed")
    seed_resource.actors.add(actor)
    monkeypatch.setattr(
        Jable,
        "search",
        lambda self, keyword, page=1: [
            {
                "avid": "REC-905-A",
                "title": "Feedback Candidate",
                "detail_url": "https://jable.tv/videos/rec-905-a/",
                "cover_url": "https://img/rec-905-a.jpg",
                "metrics": {"views": 3200, "likes": 350},
            }
        ],
    )
    response = api_client.get("/nassav/api/recommendations/", {"limit": 1})
    snapshot_id = response.json()["data"]["items"][0]["snapshot_id"]

    api_client.post(
        "/nassav/api/recommendations/feedback",
        {"snapshot_id": snapshot_id, "avid": "REC-905-A", "feedback": "dislike"},
        format="json",
    )
    profile = recommendation_feedback_repository.build_learning_profile()
    assert profile.avid_scores == {}
    assert profile.seed_scores["actor:Alice"] < 0
    assert "REC-905-A" in profile.blocked_avids


def test_seed_weight_factor_uses_seed_occurrence_tiers_with_custom_preferences():
    from nassav.recommendation import (
        RecommendationCandidate,
        RecommendationRequest,
        RecommendationSeed,
        SeedWeightFactor,
    )

    factor = SeedWeightFactor(actor_multiplier=1.0, genre_multiplier=1.0)
    candidate = RecommendationCandidate(
        avid="REC-901",
        title="Tiered Seed Candidate",
        detail_url="https://jable.tv/videos/rec-901/",
        cover_url="https://img/rec-901.jpg",
    )
    candidate.add_seed(
        RecommendationSeed(
            seed_type="actor",
            value="Alice",
            weight=1.0,
            source="local_top_actor",
        )
    )
    common_tiers = {
        "actor:Alice": "high",
    }
    rare_request = RecommendationRequest(
        seed_occurrence_tiers=common_tiers,
        actor_preference="rare",
        genre_preference="rare",
    )
    familiar_request = RecommendationRequest(
        seed_occurrence_tiers=common_tiers,
        actor_preference="familiar",
        genre_preference="familiar",
    )

    rare_score, _ = factor.score(candidate, rare_request)
    familiar_score, _ = factor.score(candidate, familiar_request)

    assert rare_score < familiar_score
