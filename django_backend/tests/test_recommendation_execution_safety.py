from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from nassav.recommendation.entities import (
    RecommendationCandidate,
    RecommendationRequest,
)
from nassav.recommendation.jable_search import JableSearchRecommender
from nassav.source import Jable
from nassav.source.search_contracts import SourceSearchError, SourceSearchUnavailable


def test_failed_details_consume_one_shared_budget_across_topups():
    source = Mock()
    source.get_video_detail.return_value = {}
    algorithm = JableSearchRecommender(
        jable=source, candidate_inventory=Mock(), seed_provider=Mock()
    )
    request = RecommendationRequest(detail_enrichment_limit=2)
    candidates = [
        RecommendationCandidate(
            str(i), "", "", "", raw_metrics={"discovery_sources": ["hot"]}
        )
        for i in range(5)
    ]
    algorithm.enrich_candidates(candidates, request)
    algorithm.enrich_candidates(candidates, request)
    assert source.get_video_detail.call_count == 2
    assert len(request.detail_attempted_avids) == 2


def test_strict_source_distinguishes_failure_from_empty_results():
    source = Jable(strict_failures=True, page_fetcher=Mock())
    source.page_fetcher.for_lookup.return_value = source.page_fetcher
    source.page_fetcher.fetch.return_value = SimpleNamespace(
        ok=False, failure="timeout", html=None
    )
    with pytest.raises(SourceSearchError, match="timeout"):
        source.search("Alice", force_refresh=True)
    legacy = Jable(page_fetcher=source.page_fetcher)
    assert legacy.search("Alice", force_refresh=True) == []


def test_recommendation_refuses_disabled_source(settings):
    from nassav.composition import build_recommendation_manager

    settings.SOURCE_CONFIG = {"jable": {"weight": 0}}
    manager = build_recommendation_manager()
    with pytest.raises(SourceSearchUnavailable):
        manager.build_recommender("jable_page_lookup", manager.get_strategy())


def test_recommendation_source_uses_global_page_proxy(settings):
    from nassav.composition import build_recommendation_manager

    settings.SOURCE_CONFIG = {"jable": {"weight": 1}}
    settings.PROXY_ENABLED = True
    settings.PROXY_URL = "http://127.0.0.1:19091"
    settings.DOWNLOAD_PROXY_URL = "http://127.0.0.1:19092"
    manager = build_recommendation_manager()
    algorithm = manager.build_recommender("jable_page_lookup", manager.get_strategy())
    assert algorithm.jable.proxy == settings.PROXY_URL
    assert algorithm.jable.strict_failures


def test_active_seed_blacklist_excludes_unverified_candidates_before_trimming():
    algorithm = JableSearchRecommender(
        jable=Mock(), candidate_inventory=Mock(), seed_provider=Mock()
    )
    request = RecommendationRequest(limit=1, seed_blacklist_active=True)
    unknown = RecommendationCandidate("UNKNOWN", "", "", "", total_score=100)
    verified = RecommendationCandidate(
        "VERIFIED", "", "", "", raw_metrics={"detail_enriched": True}
    )
    assert algorithm.rank_and_trim([unknown, verified], request) == [verified]
    assert request.unverified_candidate_count == 1
    request.seed_blacklist_active = False
    assert algorithm.rank_and_trim([unknown, verified], request) == [unknown]
