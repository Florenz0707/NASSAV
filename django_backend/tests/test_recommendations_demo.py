import pytest


@pytest.mark.django_db
def test_recommendations_demo_endpoint_runs_with_empty_search(
    api_client, monkeypatch, resource_factory, actor_factory, genre_factory
):
    from nassav.source import Jable

    actor = actor_factory(name="Alice")
    genre = genre_factory(name="中文字幕")

    resource = resource_factory(avid="SEED-001", original_title="Seed Resource")
    resource.actors.add(actor)
    resource.genres.add(genre)

    monkeypatch.setattr(Jable, "search", lambda self, keyword, page=1: [])

    response = api_client.get("/nassav/api/recommendations/demo")
    assert response.status_code == 200

    body = response.json()
    assert body["code"] == 200
    assert "items" in body["data"]
    assert "seeds" in body["data"]
    assert body["data"]["summary"]["seed_count"] >= 2
    assert body["data"]["items"] == []


@pytest.mark.django_db
def test_recommendations_demo_endpoint_merges_scores_and_filters_existing(
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
        "/nassav/api/recommendations/demo",
        {"actor_seed_limit": 1, "genre_seed_limit": 1, "per_seed_limit": 10},
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
