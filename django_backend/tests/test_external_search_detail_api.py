import pytest

from nassav.external_search import external_search_service
from nassav.models import ActorSourceMapping, GenreSourceMapping


class _FakeJableSource:
    def __init__(self):
        self.model_calls = []
        self.search_calls = []
        self.tag_calls = []
        self.category_calls = []

    def get_source_name(self):
        return "Jable"

    def get_model_videos(
        self, model_slug, page=1, sort_by="video_viewed", force_refresh=False
    ):
        self.model_calls.append((model_slug, page, sort_by, force_refresh))
        if page > 1:
            return []
        return [
            {
                "avid": "JAB-100",
                "title": "Mapped actor result",
                "detail_url": "https://jable.tv/videos/jab-100/",
                "cover_url": "https://img/jab-100.jpg",
                "source": "Jable",
                "metrics": {"views": 500, "likes": 11},
            }
        ]

    def search(self, keyword, page=1, force_refresh=False):
        self.search_calls.append((keyword, page, force_refresh))
        if page > 1:
            return []
        return [
            {
                "avid": "JAB-101",
                "title": f"Search result {keyword}",
                "detail_url": "https://jable.tv/videos/jab-101/",
                "cover_url": "https://img/jab-101.jpg",
                "source": "Jable",
                "metrics": {"views": 300, "likes": 8},
            }
        ]

    def get_tag_videos(self, tag_slug, page=1, force_refresh=False):
        self.tag_calls.append((tag_slug, page, force_refresh))
        if page > 1:
            return []
        return [
            {
                "avid": "GEN-901",
                "title": "Tag result",
                "detail_url": "https://jable.tv/videos/gen-901/",
                "cover_url": "https://img/gen-901.jpg",
                "source": "Jable",
                "metrics": {"views": 200, "likes": 3},
            }
        ]

    def get_category_videos(self, category_slug, page=1, force_refresh=False):
        self.category_calls.append((category_slug, page, force_refresh))
        return []


@pytest.mark.django_db
def test_external_search_service_prefers_actor_mapping(
    actor_factory, monkeypatch, settings
):
    actor = actor_factory(name="Alice")
    ActorSourceMapping.objects.create(
        actor=actor,
        source_name="jable",
        source_actor_slug="alice-mapped",
    )

    fake_source = _FakeJableSource()
    monkeypatch.setattr(
        "nassav.external_search.source_manager.sources",
        {"Jable": fake_source},
    )
    monkeypatch.setattr(settings, "EXTERNAL_SEARCH_CACHE_ENABLED", False, raising=False)
    monkeypatch.setattr(settings, "EXTERNAL_SEARCH_FETCH_PAGES", 1, raising=False)

    result = external_search_service.search_actor_detail(
        actor_id=actor.id,
        source_name="jable",
        page=1,
        page_size=20,
        ordering="-views",
    )

    assert result.meta["implemented"] is True
    assert result.pagination["total"] == 1
    assert result.items[0]["avid"] == "JAB-100"
    assert fake_source.model_calls == [("alice-mapped", 1, "video_viewed", False)]
    assert fake_source.search_calls == []


@pytest.mark.django_db
def test_external_search_service_uses_genre_tag_mapping(
    genre_factory, monkeypatch, settings
):
    genre = genre_factory(name="中文字幕")
    GenreSourceMapping.objects.create(
        genre=genre,
        source_name="jable",
        source_genre_slug="zh",
        source_genre_url="https://jable.tv/tags/zh/",
    )

    fake_source = _FakeJableSource()
    monkeypatch.setattr(
        "nassav.external_search.source_manager.sources",
        {"Jable": fake_source},
    )
    monkeypatch.setattr(settings, "EXTERNAL_SEARCH_CACHE_ENABLED", False, raising=False)
    monkeypatch.setattr(settings, "EXTERNAL_SEARCH_FETCH_PAGES", 1, raising=False)

    result = external_search_service.search_genre_detail(
        genre_id=genre.id,
        source_name="jable",
        page=1,
        page_size=20,
        ordering="-views",
    )

    assert result.meta["implemented"] is True
    assert result.pagination["total"] == 1
    assert result.items[0]["avid"] == "GEN-901"
    assert fake_source.tag_calls == [("zh", 1, False)]


@pytest.mark.django_db
def test_actor_detail_api_propagates_force_refresh_query(
    actor_factory, api_client, monkeypatch
):
    actor = actor_factory(name="Actor Force Refresh")
    captured = {}

    def _fake_search_actor_detail(**kwargs):
        captured.update(kwargs)
        return type(
            "Result",
            (),
            {
                "items": [],
                "pagination": {
                    "total": 0,
                    "page": 1,
                    "page_size": 20,
                    "pages": 0,
                },
                "meta": {
                    "actor": {
                        "id": actor.id,
                        "name": actor.name,
                        "resource_count": 0,
                        "avatar_url": None,
                        "avatar_filename": None,
                    },
                    "source": "jable",
                    "implemented": True,
                    "ordering": "-views",
                    "fetch_pages": 1,
                    "cache": {
                        "enabled": True,
                        "hit": False,
                        "force_refresh": True,
                    },
                },
            },
        )()

    monkeypatch.setattr(
        "nassav.views.external_search_service.search_actor_detail",
        _fake_search_actor_detail,
    )

    resp = api_client.get(
        f"/nassav/api/actors/{actor.id}/detail",
        {"force_refresh": "true"},
    )
    assert resp.status_code == 200
    assert captured.get("force_refresh") is True


@pytest.mark.django_db
def test_actor_detail_api_returns_external_results(
    actor_factory, api_client, monkeypatch
):
    actor = actor_factory(name="Actor API")

    def _fake_search_actor_detail(**kwargs):
        _ = kwargs
        return type(
            "Result",
            (),
            {
                "items": [
                    {
                        "avid": "API-001",
                        "source_title": "API Item",
                        "source": "Jable",
                        "metrics": {"views": 10, "likes": 1},
                    }
                ],
                "pagination": {
                    "total": 1,
                    "page": 1,
                    "page_size": 10,
                    "pages": 1,
                },
                "meta": {
                    "actor": {
                        "id": actor.id,
                        "name": actor.name,
                        "resource_count": 0,
                        "avatar_url": None,
                        "avatar_filename": None,
                    },
                    "source": "jable",
                    "implemented": True,
                    "ordering": "-views",
                    "fetch_pages": 1,
                    "cache": {"enabled": False, "hit": False},
                },
            },
        )()

    monkeypatch.setattr(
        "nassav.views.external_search_service.search_actor_detail",
        _fake_search_actor_detail,
    )

    resp = api_client.get(
        f"/nassav/api/actors/{actor.id}/detail",
        {"page_size": 10},
    )
    assert resp.status_code == 200

    body = resp.json()
    assert body["code"] == 200
    assert body["pagination"]["total"] == 1
    assert body["data"]["detail"]["id"] == actor.id
    assert body["data"]["external_results"][0]["avid"] == "API-001"


@pytest.mark.django_db
def test_actor_detail_api_supports_non_jable_placeholder(actor_factory, api_client):
    actor = actor_factory(name="Actor Placeholder")

    resp = api_client.get(
        f"/nassav/api/actors/{actor.id}/detail",
        {"source": "missav", "page": 1, "page_size": 10},
    )
    assert resp.status_code == 200

    body = resp.json()
    assert body["code"] == 200
    assert body["data"]["external_source"] == "missav"
    assert body["data"]["external_meta"]["implemented"] is False
    assert body["data"]["external_results"] == []
    assert body["pagination"]["total"] == 0


@pytest.mark.django_db
def test_genre_detail_api_returns_404_for_missing_genre(api_client):
    resp = api_client.get("/nassav/api/genres/999999/detail")
    assert resp.status_code == 404
    body = resp.json()
    assert body["code"] == 404
