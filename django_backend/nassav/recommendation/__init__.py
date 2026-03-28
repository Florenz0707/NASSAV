from nassav.source import Jable

from .entities import (
    RecommendationCandidate,
    RecommendationRequest,
    RecommendationRun,
    RecommendationSeed,
)
from .factors import MultiSeedBonusFactor, PopularityFactor, SeedWeightFactor
from .jable_search import JableSearchRecommender
from .seeds import LocalPreferenceSeedProvider

__all__ = [
    "JableSearchRecommender",
    "LocalPreferenceSeedProvider",
    "MultiSeedBonusFactor",
    "PopularityFactor",
    "RecommendationCandidate",
    "RecommendationRequest",
    "RecommendationRun",
    "RecommendationSeed",
    "SeedWeightFactor",
    "build_demo_recommender",
]


def build_demo_recommender() -> JableSearchRecommender:
    return JableSearchRecommender(
        jable=Jable(),
        seed_provider=LocalPreferenceSeedProvider(),
        factors=[
            SeedWeightFactor(),
            MultiSeedBonusFactor(),
            PopularityFactor(),
        ],
    )
