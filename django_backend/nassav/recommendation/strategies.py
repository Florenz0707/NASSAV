from collections.abc import Callable
from dataclasses import dataclass, field

from .factors import MultiSeedBonusFactor, PopularityFactor, SeedWeightFactor
from .seeds import SeedProvider
from .seeds import LocalPreferenceSeedProvider
from .factors import RecommendationFactor


@dataclass
class RecommendationStrategy:
    strategy_id: str
    name: str
    description: str
    supported_recommenders: list[str]
    seed_provider_builder: Callable[[], SeedProvider]
    factor_builders: list[Callable[[], RecommendationFactor]] = field(
        default_factory=list
    )
    default_request_overrides: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.strategy_id,
            "name": self.name,
            "description": self.description,
            "supported_recommenders": list(self.supported_recommenders),
            "default_request_overrides": dict(self.default_request_overrides),
        }


def build_local_demo_strategy() -> RecommendationStrategy:
    return RecommendationStrategy(
        strategy_id="local_demo",
        name="Local Demo",
        description="基于本地高频演员与类别的 Jable 搜索推荐 demo。",
        supported_recommenders=["jable_search"],
        seed_provider_builder=LocalPreferenceSeedProvider,
        factor_builders=[
            SeedWeightFactor,
            MultiSeedBonusFactor,
            PopularityFactor,
        ],
        default_request_overrides={
            "limit": 12,
            "per_seed_limit": 12,
            "actor_seed_limit": 5,
            "genre_seed_limit": 5,
            "seed_types": ["actor", "genre"],
            "exclude_existing": True,
        },
    )
