import pytest


@pytest.mark.django_db
def test_jable_page_lookup_recommender_uses_genre_tag_mapping(
    genre_factory,
    monkeypatch,
    resource_factory,
):
    from nassav.models import GenreSourceMapping
    from nassav.recommendation.entities import RecommendationRequest
    from nassav.recommendation.jable_page_lookup import JablePageLookupRecommender
    from nassav.recommendation.seeds import LocalPreferenceSeedProvider
    from nassav.source import Jable

    genre = genre_factory(name="中文字幕")
    seed_resource = resource_factory(avid="SEED-GENRE-001", original_title="Seed")
    seed_resource.genres.add(genre)

    GenreSourceMapping.objects.create(
        genre=genre,
        source_name="jable",
        source_genre_name="中文字幕",
        source_genre_slug="chinese-subtitle",
        source_genre_url="https://jable.tv/tags/chinese-subtitle/",
    )

    jable = Jable()
    calls = []

    def fake_get_tag_videos(tag_slug, page=1):
        calls.append(("tag", tag_slug, page))
        if page == 1:
            return [
                {
                    "avid": "REC-TAG-001",
                    "title": "Tag Page One",
                    "detail_url": "https://jable.tv/videos/rec-tag-001/",
                    "cover_url": "https://img/rec-tag-001.jpg",
                    "metrics": {"views": 100, "likes": 10},
                }
            ]
        return []

    monkeypatch.setattr(jable, "get_tag_videos", fake_get_tag_videos)
    monkeypatch.setattr(jable, "get_category_videos", lambda slug, page=1: [])
    monkeypatch.setattr(jable, "search", lambda keyword, page=1: [])
    monkeypatch.setattr(jable, "discover_hot_items", lambda page=1: [])
    monkeypatch.setattr(jable, "discover_latest_updates", lambda page=1: [])

    recommender = JablePageLookupRecommender(
        jable=jable,
        seed_provider=LocalPreferenceSeedProvider(),
        max_pages_per_query=2,
    )
    request = RecommendationRequest(
        limit=1,
        per_seed_limit=5,
        actor_seed_limit=0,
        genre_seed_limit=1,
        seed_types=["genre"],
        include_hot_board=False,
        include_latest_updates=False,
    )

    run = recommender.recommend(request)

    assert calls == [("tag", "chinese-subtitle", 1)]
    assert [item.avid for item in run.items] == ["REC-TAG-001"]


@pytest.mark.django_db
def test_jable_page_lookup_recommender_falls_back_to_search_without_mapping(
    genre_factory,
    monkeypatch,
    resource_factory,
):
    from nassav.recommendation.entities import RecommendationRequest
    from nassav.recommendation.jable_page_lookup import JablePageLookupRecommender
    from nassav.recommendation.seeds import LocalPreferenceSeedProvider
    from nassav.source import Jable

    genre = genre_factory(name="中文字幕")
    seed_resource = resource_factory(avid="SEED-GENRE-002", original_title="Seed")
    seed_resource.genres.add(genre)

    jable = Jable()
    calls = []

    def fake_search(keyword, page=1):
        calls.append((keyword, page))
        if page == 1:
            return [
                {
                    "avid": "REC-SEARCH-001",
                    "title": "Search Fallback One",
                    "detail_url": "https://jable.tv/videos/rec-search-001/",
                    "cover_url": "https://img/rec-search-001.jpg",
                    "metrics": {"views": 100, "likes": 10},
                }
            ]
        return []

    monkeypatch.setattr(jable, "get_tag_videos", lambda slug, page=1: [])
    monkeypatch.setattr(jable, "get_category_videos", lambda slug, page=1: [])
    monkeypatch.setattr(jable, "search", fake_search)
    monkeypatch.setattr(jable, "discover_hot_items", lambda page=1: [])
    monkeypatch.setattr(jable, "discover_latest_updates", lambda page=1: [])

    recommender = JablePageLookupRecommender(
        jable=jable,
        seed_provider=LocalPreferenceSeedProvider(),
        max_pages_per_query=2,
    )
    request = RecommendationRequest(
        limit=1,
        per_seed_limit=5,
        actor_seed_limit=0,
        genre_seed_limit=1,
        seed_types=["genre"],
        include_hot_board=False,
        include_latest_updates=False,
    )

    run = recommender.recommend(request)

    assert calls == [("中文字幕", 1)]
    assert [item.avid for item in run.items] == ["REC-SEARCH-001"]
