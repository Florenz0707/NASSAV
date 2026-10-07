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


def budget_algorithm(clock, *, limit=12):
    from nassav.recommendation.execution_budget import RecommendationExecutionBudget
    from nassav.page_fetching.proxy_server import OrderedProxyServer

    budget = RecommendationExecutionBudget(300, clock=lambda: clock[0])
    source = Mock()

    def detail(*args, **kwargs):
        clock[0] += 20.6
        budget.check()
        return {"actors": ["Allowed"], "genres": ["Allowed"]}

    source.get_video_detail.side_effect = detail
    algorithm = JableSearchRecommender(
        jable=source,
        candidate_inventory=Mock(),
        seed_provider=Mock(),
        execution_budget=budget,
        check=budget.check,
        proxy_server=OrderedProxyServer(),
    )
    request = RecommendationRequest(limit=limit, seed_blacklist_active=True)
    candidates = [
        RecommendationCandidate(
            str(i), "", "", "", raw_metrics={"discovery_sources": ["hot"]}
        )
        for i in range(24)
    ]
    return algorithm, source, request, candidates


def test_goal_stops_detail_work_before_attempt_ceiling():
    clock = [0.0]
    algorithm, source, request, candidates = budget_algorithm(clock)
    algorithm.enrich_candidates(candidates, request)
    assert source.get_video_detail.call_count == 12
    assert len(request.detail_attempted_avids) == 12
    assert len(algorithm.rank_and_trim(candidates, request)) == 12


def test_soft_budget_keeps_only_completed_verified_details():
    clock = [114.0]
    algorithm, source, request, candidates = budget_algorithm(clock)
    # Replay the recorded recall cost within the same whole-job budget.
    algorithm.execution_budget.started = 0
    algorithm.execution_budget.deadline = 270
    algorithm.enrich_candidates(candidates, request)
    assert request.completion_reason == "network_budget"
    result = algorithm.rank_and_trim(candidates, request)
    assert 0 < len(result) < 12
    assert all(item.raw_metrics.get("detail_enriched") for item in result)
    assert len(request.detail_attempted_avids) <= 24
    assert source.get_video_detail.call_count < 24


def test_soft_partial_requires_verification_even_without_seed_blacklist():
    algorithm = JableSearchRecommender(
        jable=Mock(), candidate_inventory=Mock(), seed_provider=Mock()
    )
    request = RecommendationRequest(completion_reason="network_budget")
    assert (
        algorithm.rank_and_trim(
            [RecommendationCandidate("UNKNOWN", "", "", "")], request
        )
        == []
    )


def test_hard_timeout_and_cancel_are_not_swallowed_by_detail_batches():
    from nassav.task_network import TaskNetworkTimeout
    from nassav.recommendation.jobs import RecommendationStopped

    for error in [TaskNetworkTimeout("hard deadline"), RecommendationStopped("cancel")]:
        algorithm, source, request, candidates = budget_algorithm([0.0])
        source.get_video_detail.side_effect = error
        with pytest.raises(type(error)):
            algorithm.enrich_candidates(candidates, request)


def test_blocked_details_do_not_count_towards_target():
    algorithm, source, request, candidates = budget_algorithm([0.0], limit=2)
    request.blocked_seed_name_keys = {("actor", "blocked")}
    source.get_video_detail.side_effect = [
        {"actors": ["Blocked"]},
        {"actors": ["Allowed"]},
        {"actors": ["Allowed"]},
        {"actors": ["Allowed"]},
    ]
    algorithm.enrich_candidates(candidates, request)
    assert source.get_video_detail.call_count == 4
    result = algorithm.rank_and_trim(
        algorithm.filter_blocklisted_candidates(candidates, request), request
    )
    assert len(result) == 2
    assert all("Blocked" not in item.raw_metrics["detail"]["actors"] for item in result)
