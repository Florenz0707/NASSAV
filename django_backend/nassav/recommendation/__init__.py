"""Lazy public exports keep pure recommendation algorithms infrastructure-free."""

from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .entities import (
        RecommendationCandidate,
        RecommendationExecution,
        RecommendationRequest,
        RecommendationRun,
        RecommendationSeed,
    )
    from .factors import (
        DiscoverySourceFactor,
        FeedbackSignalFactor,
        MultiSeedBonusFactor,
        NoveltyFactor,
        PopularityFactor,
        SearchRankFactor,
        SeedWeightFactor,
    )
    from .feedback import (
        RecommendationFeedbackError,
        RecommendationLearningProfile,
        recommendation_feedback_repository,
    )
    from .jable_page_lookup import JablePageLookupRecommender
    from .jable_search import JableSearchRecommender
    from .manager import (
        RecommendationManagerError,
        RecommenderManager,
        recommender_manager,
    )
    from .seeds import LocalPreferenceSeedProvider
    from .strategies import (
        RecommendationStrategy,
        build_local_preference_strategy,
    )


_EXPORTS = {
    "RecommendationCandidate": ("entities", "RecommendationCandidate"),
    "RecommendationExecution": ("entities", "RecommendationExecution"),
    "RecommendationRequest": ("entities", "RecommendationRequest"),
    "RecommendationRun": ("entities", "RecommendationRun"),
    "RecommendationSeed": ("entities", "RecommendationSeed"),
    "DiscoverySourceFactor": ("factors", "DiscoverySourceFactor"),
    "FeedbackSignalFactor": ("factors", "FeedbackSignalFactor"),
    "MultiSeedBonusFactor": ("factors", "MultiSeedBonusFactor"),
    "NoveltyFactor": ("factors", "NoveltyFactor"),
    "PopularityFactor": ("factors", "PopularityFactor"),
    "SearchRankFactor": ("factors", "SearchRankFactor"),
    "SeedWeightFactor": ("factors", "SeedWeightFactor"),
    "RecommendationFeedbackError": ("feedback", "RecommendationFeedbackError"),
    "RecommendationLearningProfile": ("feedback", "RecommendationLearningProfile"),
    "recommendation_feedback_repository": (
        "feedback",
        "recommendation_feedback_repository",
    ),
    "JablePageLookupRecommender": ("jable_page_lookup", "JablePageLookupRecommender"),
    "JableSearchRecommender": ("jable_search", "JableSearchRecommender"),
    "RecommendationManagerError": ("manager", "RecommendationManagerError"),
    "RecommenderManager": ("manager", "RecommenderManager"),
    "recommender_manager": ("manager", "recommender_manager"),
    "LocalPreferenceSeedProvider": ("seeds", "LocalPreferenceSeedProvider"),
    "RecommendationStrategy": ("strategies", "RecommendationStrategy"),
    "build_local_preference_strategy": (
        "strategies",
        "build_local_preference_strategy",
    ),
}
__all__ = [
    "JableSearchRecommender",
    "JablePageLookupRecommender",
    "LocalPreferenceSeedProvider",
    "FeedbackSignalFactor",
    "DiscoverySourceFactor",
    "MultiSeedBonusFactor",
    "NoveltyFactor",
    "PopularityFactor",
    "RecommendationCandidate",
    "RecommendationExecution",
    "RecommendationFeedbackError",
    "RecommendationLearningProfile",
    "RecommendationManagerError",
    "RecommendationRequest",
    "RecommendationRun",
    "RecommendationSeed",
    "RecommendationStrategy",
    "RecommenderManager",
    "SearchRankFactor",
    "SeedWeightFactor",
    "build_local_preference_strategy",
    "recommendation_feedback_repository",
    "recommender_manager",
]


def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(name)
    module, attribute = _EXPORTS[name]
    value = getattr(import_module(f".{module}", __name__), attribute)
    globals()[name] = value
    return value
