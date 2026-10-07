"""Public search/recommendation behavior under provider-independent concurrency."""

import threading
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from django.core.cache import cache
from nassav.external_search import (
    ExternalSearchService,
    ExternalSourceAdapter,
    SearchCapability,
)
from nassav.page_fetching.proxy_server import OrderedProxyServer
from nassav.recommendation.entities import (
    RecommendationCandidate,
    RecommendationRequest,
    RecommendationSeed,
)
from nassav.recommendation.jable_search import JableSearchRecommender
from nassav.source.search_contracts import SourceSearchError
from nassav.task_network import TaskNetworkControl


class ConcurrentListing(ExternalSourceAdapter):
    source_name = "example"
    implemented = True

    def __init__(self, fetch):
        self.fetch = fetch

    def is_enabled(self):
        return True

    def cache_context(self):
        return "example.test", "direct"

    def capability(self):
        return SearchCapability(self.source_name, "Example", native_order=True)

    def search_actor_items(self, *, actor, page, **kwargs):
        return self.fetch(page)

    def search_genre_items(self, *, genre, page, **kwargs):
        return self.fetch(page)


def search(service, entity, progress=None, check=None):
    return service.search_actor_detail(
        actor_id=entity.pk,
        source_name="example",
        page=1,
        page_size=20,
        ordering="-views",
        on_progress=progress,
        should_cancel=check,
    )


@pytest.mark.django_db
def test_external_first_page_precedes_parallel_window_and_ordered_snapshots(
    actor_factory, settings
):
    settings.EXTERNAL_SEARCH_FETCH_PAGES = 3
    settings.EXTERNAL_SEARCH_CACHE_ENABLED = False
    third_started = threading.Event()
    snapshots = []

    def fetch(page):
        if page == 2:
            assert third_started.wait(2)
        if page == 3:
            third_started.set()
        if page > 1:
            assert snapshots[0] == (1, ["AV-1"])
        return [{"avid": f"AV-{page}"}, {"avid": "AV-1"}]

    service = ExternalSearchService(
        adapters={"example": ConcurrentListing(fetch)},
        proxy_server=OrderedProxyServer(2),
    )
    result = search(
        service,
        actor_factory(),
        lambda r: snapshots.append(
            (r.meta["pages_completed"], [i["avid"] for i in r.collected_items])
        ),
    )
    assert snapshots == [
        (1, ["AV-1"]),
        (2, ["AV-1", "AV-2"]),
        (3, ["AV-1", "AV-2", "AV-3"]),
    ]
    assert [i["avid"] for i in result.items] == ["AV-1", "AV-2", "AV-3"]


@pytest.mark.django_db
def test_empty_page_discards_later_speculative_failure(actor_factory, settings):
    settings.EXTERNAL_SEARCH_FETCH_PAGES = 7
    settings.EXTERNAL_SEARCH_CACHE_ENABLED = False
    speculative_started = threading.Event()
    calls = []

    def fetch(page):
        calls.append(page)
        if page == 1:
            return [{"avid": "AV-1"}]
        if page == 2:
            assert speculative_started.wait(2)
            return []
        speculative_started.set()
        raise SourceSearchError("later_page_error")

    service = ExternalSearchService(
        adapters={"example": ConcurrentListing(fetch)},
        proxy_server=OrderedProxyServer(2),
    )
    assert len(search(service, actor_factory()).items) == 1
    assert sorted(calls) == [1, 2, 3]


@pytest.mark.django_db
def test_failure_keeps_ordered_partial_results_without_success_cache(
    actor_factory, settings
):
    settings.EXTERNAL_SEARCH_FETCH_PAGES = 3
    settings.EXTERNAL_SEARCH_CACHE_ENABLED = True
    cache.clear()
    seen, calls = [], []

    def fetch(page):
        calls.append(page)
        if page == 3:
            raise SourceSearchError("source_timeout")
        return [{"avid": f"AV-{page}"}]

    service = ExternalSearchService(
        adapters={"example": ConcurrentListing(fetch)},
        proxy_server=OrderedProxyServer(2),
    )
    actor = actor_factory()
    for _ in range(2):
        with pytest.raises(SourceSearchError):
            search(service, actor, lambda r: seen.append(r.meta["pages_completed"]))
    assert seen == [1, 2, 1, 2] and calls.count(1) == 2
    cache.clear()


@pytest.mark.django_db
def test_cancel_after_first_snapshot_does_not_dispatch_window(actor_factory, settings):
    settings.EXTERNAL_SEARCH_FETCH_PAGES = 5
    settings.EXTERNAL_SEARCH_CACHE_ENABLED = False
    cancelled = threading.Event()
    calls = []

    def check():
        if cancelled.is_set():
            raise ValueError("cancelled")

    def fetch(page):
        calls.append(page)
        return [{"avid": f"AV-{page}"}]

    service = ExternalSearchService(
        adapters={"example": ConcurrentListing(fetch)},
        proxy_server=OrderedProxyServer(2),
    )
    with pytest.raises(ValueError, match="cancelled"):
        search(service, actor_factory(), lambda r: cancelled.set(), check)
    assert calls == [1]


def candidate(avid):
    return RecommendationCandidate(
        avid, "", "", "", raw_metrics={"discovery_sources": ["hot"]}
    )


def test_recommendation_details_are_isolated_and_merge_on_coordinator_with_shared_budget():
    second_started = threading.Event()
    created, closed, requested, merges = [], [], [], []
    main_thread = threading.get_ident()

    @contextmanager
    def scope(check):
        source = SimpleNamespace()
        created.append(source)

        def detail(avid, url, **kwargs):
            requested.append(avid)
            if avid == "A":
                assert second_started.wait(2)
            else:
                second_started.set()
            check()
            return {} if avid == "B" else {"title": avid}

        source.get_video_detail = detail
        try:
            yield source
        finally:
            closed.append(source)

    class Algorithm(JableSearchRecommender):
        def _apply_video_detail(self, *args):
            merges.append(threading.get_ident())
            super()._apply_video_detail(*args)

    algorithm = Algorithm(
        jable=Mock(),
        seed_provider=Mock(),
        candidate_inventory=Mock(),
        proxy_server=OrderedProxyServer(2),
        source_scope=scope,
    )
    request = RecommendationRequest(detail_enrichment_limit=2)
    values = [candidate("A"), candidate("A"), candidate("B"), candidate("C")]
    algorithm.enrich_candidates(values, request)
    algorithm.enrich_candidates(values, request)
    assert sorted(requested) == ["A", "B"]
    assert request.detail_attempted_avids == {"A", "B"}
    assert len(created) == len(closed) == 2 and created[0] is not created[1]
    assert merges == [main_thread]
    assert values[0].raw_metrics["detail_enriched"]
    assert not values[2].raw_metrics.get("detail_enriched")


def test_recommendation_seeds_overlap_and_merge_in_original_order():
    second_started = threading.Event()
    sources, closed = [], []

    @contextmanager
    def scope(check):
        source = SimpleNamespace()
        sources.append(source)

        def fetch(keyword, **kwargs):
            if keyword == "Alice":
                assert second_started.wait(2)
            else:
                second_started.set()
            check()
            return [{"avid": "SAME", "title": keyword}, {"avid": keyword.upper()}]

        source.search = fetch
        try:
            yield source
        finally:
            closed.append(source)

    algorithm = JableSearchRecommender(
        jable=Mock(),
        seed_provider=Mock(),
        candidate_inventory=Mock(),
        max_pages_per_query=1,
        proxy_server=OrderedProxyServer(2),
        source_scope=scope,
    )
    seeds = [
        RecommendationSeed("actor", value, 1, "test") for value in ["Alice", "Bob"]
    ]
    request = RecommendationRequest(discovery_limit=0)
    result = algorithm.recall_candidates(seeds, request)
    assert [c.avid for c in result] == ["SAME", "ALICE", "BOB"]
    assert result[0].title == "Alice" and result[0].matched_seeds == seeds
    assert len(sources) == len(closed) == 2


def test_recommendation_cancel_does_not_merge_late_details():
    cancelled, release, started = (
        threading.Event(),
        threading.Event(),
        threading.Event(),
    )
    merges = []

    def check():
        if cancelled.is_set():
            raise ValueError("cancelled")

    @contextmanager
    def scope(checkpoint):
        def fetch(*args, **kwargs):
            started.set()
            assert release.wait(2)
            return {"title": "late"}

        yield SimpleNamespace(get_video_detail=fetch)

    class Algorithm(JableSearchRecommender):
        def _apply_video_detail(self, *args):
            merges.append(args)

    algorithm = Algorithm(
        jable=Mock(),
        seed_provider=Mock(),
        candidate_inventory=Mock(),
        proxy_server=OrderedProxyServer(2),
        source_scope=scope,
        check=check,
    )

    def cancel():
        assert started.wait(2)
        cancelled.set()
        release.set()

    thread = threading.Thread(target=cancel)
    thread.start()
    try:
        with pytest.raises(ValueError, match="cancelled"):
            algorithm.enrich_candidates([candidate("A")], RecommendationRequest())
    finally:
        release.set()
        thread.join(2)
    assert not merges


def test_forked_network_controls_do_not_change_sibling_deadlines():
    parent = TaskNetworkControl(lambda: None, clock=lambda: 100)
    with parent.phase(300):
        first, second = parent.fork(lambda: None), parent.fork(lambda: None)
        with first.phase(10):
            assert first.timeout(60) == 10
            assert second.timeout(60) == parent.timeout(60) == 60
        assert first.deadline == second.deadline == parent.deadline == 400


@pytest.mark.django_db(transaction=True)
def test_production_recommendation_threads_own_sources_budgets_and_connections(
    settings, monkeypatch, actor_factory
):
    from django.db import connections
    from nassav.composition import build_recommendation_manager
    from nassav.models import Actor
    from nassav.page_fetching.factory import BrowserFetchConfig
    from nassav.page_fetching.proxy_client import ProxyPageClient
    from nassav.source import Jable

    actor_factory()
    settings.BROWSER_FETCH_CONFIG = BrowserFetchConfig(
        True, "flaresolverr", "http://proxy.test:8191", 60000, max_concurrency=2
    )
    settings.SOURCE_CONFIG = {"jable": {"weight": 1}}
    settings.PROXY_ENABLED = True
    settings.PROXY_URL = "http://egress.test:7890"
    both = threading.Barrier(2)
    sources, closed_clients, closed_connections = [], [], []
    original_close = connections.close_all
    main = threading.get_ident()

    def close_connections():
        closed_connections.append(threading.get_ident())
        original_close()

    def detail(source, avid, url, **kwargs):
        sources.append(source)
        assert source.proxy == settings.PROXY_URL
        assert source.page_fetcher.browser.provider == "flaresolverr"
        assert source.task_control.timeout(60) == 60
        assert Actor.objects.count() == 1
        both.wait(timeout=3)
        source.task_control.check()
        return {"title": avid}

    monkeypatch.setattr(Jable, "get_video_detail", detail)
    monkeypatch.setattr(
        ProxyPageClient, "close", lambda client: closed_clients.append(client)
    )
    monkeypatch.setattr(connections, "close_all", close_connections)
    parent = TaskNetworkControl(lambda: Actor.objects.count())
    with parent.phase(300):
        manager = build_recommendation_manager(control=parent)
        algorithm = manager.build_recommender(
            "jable_page_lookup", manager.get_strategy()
        )
        values = [candidate("A"), candidate("B")]
        algorithm.enrich_candidates(
            values, RecommendationRequest(detail_enrichment_limit=2)
        )
        assert all(
            source.task_control.deadline == parent.deadline for source in sources
        )
    assert len(sources) == 2 and sources[0] is not sources[1]
    assert sources[0].task_control is not sources[1].task_control
    assert len(closed_clients) == len(closed_connections) == 2
    assert all(thread != main for thread in closed_connections)
    assert all(value.raw_metrics.get("detail_enriched") for value in values)


@pytest.mark.django_db(transaction=True)
def test_production_external_pages_isolate_sources_and_keep_library_presence(
    settings, monkeypatch, actor_factory, resource_factory
):
    from nassav.page_fetching.factory import BrowserFetchConfig
    from nassav.page_fetching.proxy_client import ProxyPageClient
    from nassav.source import Jable
    from nassav.source.SourceManager import source_manager

    settings.BROWSER_FETCH_CONFIG = BrowserFetchConfig(
        True, "flaresolverr", "http://proxy.test:8191", 60000, max_concurrency=2
    )
    settings.SOURCE_CONFIG = {"jable": {"weight": 1}}
    settings.EXTERNAL_SEARCH_FETCH_PAGES = 3
    settings.EXTERNAL_SEARCH_CACHE_ENABLED = False
    settings.PROXY_ENABLED = True
    settings.PROXY_URL = "http://egress.test:7890"
    actor = actor_factory()
    resource_factory(avid="AV-1")
    monkeypatch.setattr(source_manager, "sources", {"Jable": Jable()})
    third_started = threading.Event()
    sources, closed, snapshots = [], [], []

    def listing(source, kind, term, *, page, **kwargs):
        sources.append(source)
        if page == 2:
            assert third_started.wait(3)
        if page == 3:
            third_started.set()
        source.task_control.check()
        assert source.proxy == settings.PROXY_URL
        assert source.page_fetcher.browser.server is service.proxy_server
        return [{"avid": f"AV-{page}", "title": "title", "metrics": {"views": page}}]

    monkeypatch.setattr(Jable, "search_listing", listing)
    monkeypatch.setattr(ProxyPageClient, "close", lambda client: closed.append(client))
    service = ExternalSearchService()
    result = service.search_actor_detail(
        actor_id=actor.pk,
        source_name="jable",
        page=1,
        page_size=20,
        ordering="-views",
        on_progress=lambda r: snapshots.append(r.meta["pages_completed"]),
    )
    assert snapshots == [1, 2, 3]
    assert (
        len(sources) == len(closed) == 3
        and len({id(source) for source in sources}) == 3
    )
    assert len({id(source.task_control) for source in sources}) == 3
    assert [i["avid"] for i in result.items] == ["AV-3", "AV-2", "AV-1"]
    assert [i["avid"] for i in result.items if i["in_library"]] == ["AV-1"]
