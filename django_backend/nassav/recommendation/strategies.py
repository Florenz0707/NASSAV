from collections.abc import Callable
from dataclasses import dataclass, field

from .factors import (
    DiscoverySourceFactor,
    FeedbackSignalFactor,
    MultiSeedBonusFactor,
    NoveltyFactor,
    PopularityFactor,
    RecommendationFactor,
    SearchRankFactor,
    SeedWeightFactor,
)
from .seeds import LocalPreferenceSeedProvider, SeedProvider


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
    recommender_kwargs: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.strategy_id,
            "name": self.name,
            "description": self.description,
            "supported_recommenders": list(self.supported_recommenders),
            "default_request_overrides": dict(self.default_request_overrides),
        }


def build_local_preference_strategy() -> RecommendationStrategy:
    return RecommendationStrategy(
        strategy_id="local_preference",
        name="Local Preference",
        description="基于本地高频演员与类别的 Jable 搜索推荐 demo。",
        supported_recommenders=["jable_search"],
        seed_provider_builder=lambda: LocalPreferenceSeedProvider(
            watched_boost=0.6,
            favorite_boost=1.0,
            recent_boost=0.8,
            recent_days=180,
        ),
        factor_builders=[
            lambda: SeedWeightFactor(actor_multiplier=1.0, genre_multiplier=0.72),
            lambda: MultiSeedBonusFactor(bonus_per_extra=1.5),
            lambda: SearchRankFactor(max_bonus=1.8, decay=0.18),
            lambda: PopularityFactor(),
            lambda: DiscoverySourceFactor(
                hot_board_bonus=0.95, latest_updates_bonus=0.7
            ),
            lambda: FeedbackSignalFactor(avid_weight=2.5, seed_weight=1.7),
            lambda: NoveltyFactor(
                fresh_bonus=0.7,
                repeat_penalty=0.55,
                max_penalty=2.0,
                jitter_strength=0.12,
            ),
        ],
        default_request_overrides={
            "limit": 12,
            "per_seed_limit": 12,
            "actor_seed_limit": 5,
            "genre_seed_limit": 5,
            "seed_types": ["actor", "genre"],
            "exclude_existing": True,
            "include_hot_board": True,
            "include_latest_updates": True,
            "discovery_limit": 10,
        },
        recommender_kwargs={
            "diversity_penalty": 0.45,
            "actor_diversity_weight": 1.0,
            "genre_diversity_weight": 0.55,
        },
    )


def build_balanced_strategy() -> RecommendationStrategy:
    return RecommendationStrategy(
        strategy_id="balanced",
        name="Balanced",
        description="均衡使用演员与类别偏好，并通过搜索排序与多样性重排控制扎堆。",
        supported_recommenders=["jable_search"],
        seed_provider_builder=lambda: LocalPreferenceSeedProvider(
            watched_boost=0.75,
            favorite_boost=1.1,
            recent_boost=0.9,
            recent_days=150,
        ),
        factor_builders=[
            lambda: SeedWeightFactor(actor_multiplier=0.95, genre_multiplier=0.82),
            lambda: MultiSeedBonusFactor(bonus_per_extra=1.35),
            lambda: SearchRankFactor(max_bonus=2.0, decay=0.2),
            lambda: PopularityFactor(views_divisor=550000.0, likes_divisor=6000.0),
            lambda: DiscoverySourceFactor(
                hot_board_bonus=1.0, latest_updates_bonus=0.75
            ),
            lambda: FeedbackSignalFactor(avid_weight=2.3, seed_weight=1.8),
            lambda: NoveltyFactor(
                fresh_bonus=1.1,
                repeat_penalty=0.9,
                max_penalty=3.2,
                jitter_strength=0.2,
            ),
        ],
        default_request_overrides={
            "limit": 12,
            "per_seed_limit": 12,
            "actor_seed_limit": 5,
            "genre_seed_limit": 5,
            "seed_types": ["actor", "genre"],
            "exclude_existing": True,
            "include_hot_board": True,
            "include_latest_updates": True,
            "discovery_limit": 12,
        },
        recommender_kwargs={
            "diversity_penalty": 0.7,
            "actor_diversity_weight": 1.0,
            "genre_diversity_weight": 0.7,
        },
    )


def build_actor_heavy_strategy() -> RecommendationStrategy:
    return RecommendationStrategy(
        strategy_id="actor_heavy",
        name="Actor Heavy",
        description="以演员命中为主，类别只作为弱召回信号，适合演员偏好明显的库。",
        supported_recommenders=["jable_search"],
        seed_provider_builder=lambda: LocalPreferenceSeedProvider(
            watched_boost=0.8,
            favorite_boost=1.2,
            recent_boost=0.85,
            recent_days=180,
        ),
        factor_builders=[
            lambda: SeedWeightFactor(actor_multiplier=1.25, genre_multiplier=0.45),
            lambda: MultiSeedBonusFactor(bonus_per_extra=1.2),
            lambda: SearchRankFactor(max_bonus=1.8, decay=0.18),
            lambda: PopularityFactor(),
            lambda: DiscoverySourceFactor(
                hot_board_bonus=0.8, latest_updates_bonus=0.5
            ),
            lambda: FeedbackSignalFactor(avid_weight=2.6, seed_weight=1.5),
            lambda: NoveltyFactor(
                fresh_bonus=0.45,
                repeat_penalty=0.35,
                max_penalty=1.4,
                jitter_strength=0.08,
            ),
        ],
        default_request_overrides={
            "limit": 12,
            "per_seed_limit": 12,
            "actor_seed_limit": 6,
            "genre_seed_limit": 3,
            "seed_types": ["actor", "genre"],
            "exclude_existing": True,
            "include_hot_board": True,
            "include_latest_updates": True,
            "discovery_limit": 8,
        },
        recommender_kwargs={
            "diversity_penalty": 0.55,
            "actor_diversity_weight": 1.0,
            "genre_diversity_weight": 0.4,
        },
    )


def build_recent_favorite_strategy() -> RecommendationStrategy:
    return RecommendationStrategy(
        strategy_id="recent_favorite",
        name="Recent Favorite",
        description="优先使用最近新增、已观看和已收藏资源生成种子，贴近近期兴趣。",
        supported_recommenders=["jable_search"],
        seed_provider_builder=lambda: LocalPreferenceSeedProvider(
            watched_boost=1.0,
            favorite_boost=1.6,
            recent_boost=1.3,
            recent_days=90,
            only_interacted=True,
            fallback_to_all=True,
        ),
        factor_builders=[
            lambda: SeedWeightFactor(actor_multiplier=1.1, genre_multiplier=0.6),
            lambda: MultiSeedBonusFactor(bonus_per_extra=1.4),
            lambda: SearchRankFactor(max_bonus=2.1, decay=0.18),
            lambda: PopularityFactor(views_divisor=600000.0, likes_divisor=6500.0),
            lambda: DiscoverySourceFactor(
                hot_board_bonus=0.9, latest_updates_bonus=0.9
            ),
            lambda: FeedbackSignalFactor(avid_weight=2.4, seed_weight=1.9),
            lambda: NoveltyFactor(
                fresh_bonus=0.95,
                repeat_penalty=0.7,
                max_penalty=2.6,
                jitter_strength=0.16,
            ),
        ],
        default_request_overrides={
            "limit": 12,
            "per_seed_limit": 10,
            "actor_seed_limit": 6,
            "genre_seed_limit": 4,
            "seed_types": ["actor", "genre"],
            "exclude_existing": True,
            "include_hot_board": True,
            "include_latest_updates": True,
            "discovery_limit": 12,
        },
        recommender_kwargs={
            "diversity_penalty": 0.8,
            "actor_diversity_weight": 1.0,
            "genre_diversity_weight": 0.6,
        },
    )
