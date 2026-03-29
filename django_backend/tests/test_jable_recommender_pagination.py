import pytest


@pytest.mark.django_db
def test_jable_recommender_paginates_search_results(
    actor_factory,
    monkeypatch,
    resource_factory,
):
    from nassav.recommendation.entities import RecommendationRequest
    from nassav.recommendation.jable_search import JableSearchRecommender
    from nassav.recommendation.seeds import LocalPreferenceSeedProvider
    from nassav.source import Jable

    actor = actor_factory(name="Alice")
    seed_resource = resource_factory(avid="SEED-001", original_title="Seed")
    seed_resource.actors.add(actor)

    jable = Jable()
    calls = []

    def fake_search(keyword, page=1):
        calls.append((keyword, page))
        if page == 1:
            return [
                {
                    "avid": "REC-001",
                    "title": "Page One",
                    "detail_url": "https://jable.tv/videos/rec-001/",
                    "cover_url": "https://img/rec-001.jpg",
                    "metrics": {"views": 100, "likes": 10},
                }
            ]
        if page == 2:
            return [
                {
                    "avid": "REC-002",
                    "title": "Page Two",
                    "detail_url": "https://jable.tv/videos/rec-002/",
                    "cover_url": "https://img/rec-002.jpg",
                    "metrics": {"views": 90, "likes": 9},
                }
            ]
        return []

    monkeypatch.setattr(jable, "search", fake_search)
    monkeypatch.setattr(jable, "discover_hot_items", lambda page=1: [])
    monkeypatch.setattr(jable, "discover_latest_updates", lambda page=1: [])

    recommender = JableSearchRecommender(
        jable=jable,
        seed_provider=LocalPreferenceSeedProvider(),
        max_pages_per_query=3,
    )
    request = RecommendationRequest(
        limit=2,
        per_seed_limit=2,
        actor_seed_limit=1,
        genre_seed_limit=0,
        seed_types=["actor"],
        include_hot_board=False,
        include_latest_updates=False,
    )

    run = recommender.recommend(request)

    assert calls == [("Alice", 1), ("Alice", 2)]
    assert [item.avid for item in run.items] == ["REC-001", "REC-002"]


def test_jable_recommender_paginates_latest_discovery(monkeypatch):
    from nassav.recommendation.entities import RecommendationRequest
    from nassav.recommendation.jable_search import JableSearchRecommender
    from nassav.recommendation.seeds import LocalPreferenceSeedProvider
    from nassav.source import Jable

    jable = Jable()
    calls = []

    monkeypatch.setattr(jable, "discover_hot_items", lambda page=1: [])

    def fake_latest_updates(page=1):
        calls.append(page)
        if page == 1:
            return [
                {
                    "avid": "LAT-001",
                    "title": "Latest One",
                    "detail_url": "https://jable.tv/videos/lat-001/",
                    "cover_url": "https://img/lat-001.jpg",
                    "metrics": {"discovery_sources": ["latest_updates"]},
                }
            ]
        if page == 2:
            return [
                {
                    "avid": "LAT-002",
                    "title": "Latest Two",
                    "detail_url": "https://jable.tv/videos/lat-002/",
                    "cover_url": "https://img/lat-002.jpg",
                    "metrics": {"discovery_sources": ["latest_updates"]},
                }
            ]
        return []

    monkeypatch.setattr(jable, "discover_latest_updates", fake_latest_updates)

    recommender = JableSearchRecommender(
        jable=jable,
        seed_provider=LocalPreferenceSeedProvider(),
        max_pages_per_query=3,
    )
    request = RecommendationRequest(
        limit=2,
        discovery_limit=2,
        actor_seed_limit=0,
        genre_seed_limit=0,
        seed_types=[],
        include_hot_board=False,
        include_latest_updates=True,
    )

    candidates = recommender.recall_discovery_candidates(request)

    assert calls == [1, 2]
    assert [candidate.avid for candidate in candidates] == ["LAT-001", "LAT-002"]
