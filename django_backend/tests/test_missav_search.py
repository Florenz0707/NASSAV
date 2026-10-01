"""MissAV actor/genre listing contracts. Run: uv run pytest tests/test_missav_search.py -v."""

from unittest.mock import Mock
import pytest
from nassav.page_fetching import PageFetchService, PageResult
from nassav.source.MissAV import MissAV
from nassav.source.MissAVListings import listing_url, parse_listing
from nassav.source.search_contracts import SourceSearchError
from nassav.models import ActorSourceMapping, GenreSourceMapping
from nassav.external_search import external_search_service

HTML = """<title>MissAV</title><h1>Watch VR AV Online</h1>
<div class="thumbnail"><img data-src="https://images.test/test-123.jpg">
<div class="my-2"><a href="https://missav.ai/dm8/en/test-123">TEST-123 Example</a></div></div>"""


def test_listing_parser_ignores_foreign_and_navigation_links():
    html = HTML + HTML.replace(
        "https://missav.ai/dm8/en/test-123", "https://other.test/en/test-456"
    )
    items = parse_listing(html, "missav.ai")
    assert [item["avid"] for item in items] == ["TEST-123"]
    assert items[0]["source"] == "MissAV"
    assert items[0]["metrics"] == {}


@pytest.mark.parametrize("kind", ["actresses", "genres", "search"])
def test_listing_uses_existing_browser_policy(kind):
    browser = Mock(provider="byparr")
    url = listing_url("missav.ai", kind, "波多野結衣", 2, "-likes")
    browser.fetch.return_value = PageResult(
        html=HTML, final_url=url.replace("/cn/", "/dm8/cn/"), provider="byparr"
    )
    source = MissAV("http://proxy.test:8080", page_fetcher=PageFetchService(browser))
    source.browser_fetch_strategy = "browser_first"
    source.fetch_page = Mock()
    assert (
        source.search_listing(kind, "波多野結衣", page=2, ordering="-likes")[0]["avid"]
        == "TEST-123"
    )
    browser.fetch.assert_called_once_with(url, timeout_ms=60000)
    source.fetch_page.assert_not_called()
    assert "sort=saved" in url and "page=2" in url


@pytest.mark.parametrize(
    "html,final",
    [
        ("<title>Just a moment...</title>", "/en/genres/VR"),
        (HTML, "/en"),
        ("<title>MissAV</title><h1>Unknown</h1>", "/en/genres/VR"),
    ],
)
def test_invalid_listing_is_an_error(html, final):
    browser = Mock(provider="byparr")
    browser.fetch.return_value = PageResult(
        html=html, final_url="https://missav.ai" + final, provider="byparr"
    )
    source = MissAV(page_fetcher=PageFetchService(browser))
    source.browser_fetch_strategy = "browser_first"
    with pytest.raises(SourceSearchError):
        source.search_listing("genres", "VR")


class FakeMissAV:
    domain = "missav.ai"

    def __init__(self):
        self.calls = []

    def get_source_name(self):
        return "MissAV"

    def search_listing(self, kind, term, *, page, ordering, force_refresh):
        self.calls.append((kind, term, page, ordering, force_refresh))
        return parse_listing(HTML, self.domain) if page == 1 else []


@pytest.mark.django_db
@pytest.mark.parametrize("entity", ["actor", "genre"])
@pytest.mark.parametrize("mapped", [True, False])
def test_missav_mapping_and_keyword_fallback(
    entity, mapped, actor_factory, genre_factory, monkeypatch, settings
):
    obj = (
        actor_factory(name="波多野結衣")
        if entity == "actor"
        else genre_factory(name="VR")
    )
    if mapped:
        if entity == "actor":
            ActorSourceMapping.objects.create(
                actor=obj, source_name="missav", source_actor_slug="波多野結衣"
            )
        else:
            GenreSourceMapping.objects.create(
                genre=obj, source_name="missav", source_genre_slug="VR"
            )
    source = FakeMissAV()
    monkeypatch.setattr(
        "nassav.external_search.source_manager.sources", {"MissAV": source}
    )
    settings.EXTERNAL_SEARCH_CACHE_ENABLED = False
    settings.EXTERNAL_SEARCH_FETCH_PAGES = 1
    method = getattr(external_search_service, "search_" + entity + "_detail")
    result = method(
        **{entity + "_id": obj.pk},
        source_name="missav",
        page=1,
        page_size=20,
        ordering="-views",
    )
    assert result.items[0]["source"] == "MissAV"
    assert result.items[0]["in_library"] is False
    assert (
        source.calls[0][0] == ("actresses" if entity == "actor" else "genres")
        if mapped
        else source.calls[0][0] == "search"
    )
    assert source.calls[0][1].casefold() == obj.name.casefold()


@pytest.mark.django_db
def test_capabilities_and_invalid_source(actor_factory, api_client, monkeypatch):
    monkeypatch.setattr(
        "nassav.external_search.source_manager.sources", {"MissAV": FakeMissAV()}
    )
    response = api_client.get("/nassav/api/source/search-capabilities")
    assert [entry["source"] for entry in response.json()["data"]] == ["missav"]
    actor = actor_factory()
    assert (
        api_client.get(
            f"/nassav/api/actors/{actor.pk}/detail", {"source": "unknown"}
        ).status_code
        == 400
    )
    assert (
        api_client.get(
            f"/nassav/api/actors/{actor.pk}/detail", {"source": "jable"}
        ).status_code
        == 503
    )
    assert (
        api_client.get(
            f"/nassav/api/actors/{actor.pk}/detail",
            {"source": "missav", "ordering": "views"},
        ).status_code
        == 400
    )


@pytest.mark.django_db
def test_failed_search_is_not_cached(actor_factory, api_client, monkeypatch, settings):
    from django.core.cache import cache

    cache.clear()
    source = FakeMissAV()

    def fail(*args, **kwargs):
        raise SourceSearchError("provider_timeout")

    source.search_listing = Mock(side_effect=fail)
    monkeypatch.setattr(
        "nassav.external_search.source_manager.sources", {"MissAV": source}
    )
    settings.EXTERNAL_SEARCH_CACHE_ENABLED = True
    actor = actor_factory()
    for _ in range(2):
        assert (
            api_client.get(
                f"/nassav/api/actors/{actor.pk}/detail", {"source": "missav"}
            ).status_code
            == 502
        )
    assert source.search_listing.call_count == 2


@pytest.mark.django_db
def test_missav_url_mapping_preserves_case_and_decodes_names(
    actor_factory, genre_factory
):
    actor = actor_factory()
    actor_mapping = ActorSourceMapping.objects.create(
        actor=actor,
        source_name="missav",
        source_actor_url="https://missav.ai/dm8/en/actresses/%E6%B3%A2%E5%A4%9A%E9%87%8E%E7%B5%90%E8%A1%A3",
    )
    genre_mapping = GenreSourceMapping.objects.create(
        genre=genre_factory(),
        source_name="missav",
        source_genre_url="https://missav.ai/dm2093/en/genres/VR",
    )
    assert actor_mapping.source_actor_slug == "波多野結衣"
    assert genre_mapping.source_genre_slug == "VR"


def test_listing_variants_are_one_resource_with_discovered_url():
    variant = HTML.replace("/test-123", "/test-123-uncensored-leak")
    items = parse_listing(variant + HTML, "missav.ai")
    assert len(items) == 1
    assert items[0]["avid"] == "TEST-123"
    assert items[0]["detail_url"].endswith("test-123-uncensored-leak")


@pytest.mark.django_db
def test_search_loads_paired_session_before_direct_attempt(
    actor_factory, monkeypatch, settings
):
    from nassav.source.CookieRepository import source_cookie_repository

    source_cookie_repository.set_cookie(
        "MissAV", "test=session", user_agent="Paired/test"
    )
    source = MissAV(page_fetcher=PageFetchService(None))

    def fetch_listing(*args, **kwargs):
        assert source._session_snapshot.cookie == "test=session"
        assert source._session_snapshot.user_agent == "Paired/test"
        return parse_listing(HTML, source.domain)

    monkeypatch.setattr(source, "search_listing", fetch_listing)
    monkeypatch.setattr(
        "nassav.external_search.source_manager.sources", {"MissAV": source}
    )
    settings.EXTERNAL_SEARCH_FETCH_PAGES = 1
    settings.EXTERNAL_SEARCH_CACHE_ENABLED = False
    result = external_search_service.search_actor_detail(
        actor_id=actor_factory().pk,
        source_name="missav",
        page=1,
        page_size=20,
        ordering="-views",
    )
    assert result.items[0]["source"] == "MissAV"


@pytest.mark.django_db
def test_switching_sources_keeps_cached_results_separate(
    actor_factory, api_client, monkeypatch, settings
):
    from django.core.cache import cache
    from nassav.source.Jable import Jable

    cache.clear()
    missav = FakeMissAV()
    missav.search_listing = Mock(wraps=missav.search_listing)
    jable = Jable(page_fetcher=PageFetchService(None))
    jable.search_listing = Mock(
        return_value=[
            {
                "avid": "JAB-987",
                "title": "Jable result",
                "source": "Jable",
                "detail_url": "https://jable.tv/videos/jab-987/",
            }
        ]
    )
    monkeypatch.setattr(
        "nassav.external_search.source_manager.sources",
        {"MissAV": missav, "Jable": jable},
    )
    settings.EXTERNAL_SEARCH_CACHE_ENABLED = True
    settings.EXTERNAL_SEARCH_FETCH_PAGES = 1
    actor = actor_factory()
    for source, avid in [
        ("missav", "TEST-123"),
        ("jable", "JAB-987"),
        ("missav", "TEST-123"),
    ]:
        response = api_client.get(
            f"/nassav/api/actors/{actor.pk}/detail", {"source": source}
        )
        assert response.status_code == 200
        assert response.json()["data"]["external_results"][0]["avid"] == avid
    missav.search_listing.assert_called_once()
    jable.search_listing.assert_called_once()


def test_chinese_listing_path_and_empty_page():
    from nassav.source.MissAVListings import valid_listing

    assert "/cn/genres/" in listing_url("missav.ai", "genres", "VR", 1, "-views")
    assert valid_listing(
        "<title>MissAV</title><h1>搜索</h1><p>没有找到视频</p>", "missav.ai"
    )
