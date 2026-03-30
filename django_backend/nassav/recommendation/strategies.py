from collections.abc import Callable
from dataclasses import dataclass, field

from .factors import (
    DiscoverySourceFactor,
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
    parameter_profile: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.strategy_id,
            "name": self.name,
            "description": self.description,
            "supported_recommenders": list(self.supported_recommenders),
            "default_request_overrides": dict(self.default_request_overrides),
            "parameter_profile": [dict(section) for section in self.parameter_profile],
        }


def _make_section(title: str, items: list[dict]) -> dict:
    return {"title": title, "items": items}


def _make_item(key: str, value, meaning: str) -> dict:
    return {"key": key, "value": value, "meaning": meaning}


def _build_parameter_profile(
    *,
    seed_provider_params: dict,
    seed_weight_params: dict,
    multi_seed_params: dict,
    search_rank_params: dict,
    popularity_params: dict,
    discovery_params: dict,
    novelty_params: dict,
    default_request_overrides: dict,
    recommender_kwargs: dict,
) -> list[dict]:
    return [
        _make_section(
            "基础参数",
            [
                _make_item(
                    "type_preference",
                    "balanced",
                    "类型偏好：actor_heavy / balanced / genre_heavy。",
                ),
                _make_item(
                    "actor_preference",
                    "balanced",
                    "演员偏好：familiar / balanced / rare。",
                ),
                _make_item(
                    "genre_preference",
                    "balanced",
                    "类别偏好：familiar / balanced / rare。",
                ),
            ],
        ),
        _make_section(
            "种子生成",
            [
                _make_item(
                    "watched_boost",
                    seed_provider_params["watched_boost"],
                    "已观看资源对本地偏好分数的加成系数。",
                ),
                _make_item(
                    "favorite_boost",
                    seed_provider_params["favorite_boost"],
                    "已收藏资源对本地偏好分数的加成系数。",
                ),
                _make_item(
                    "recent_boost",
                    seed_provider_params["recent_boost"],
                    "最近新增资源对偏好分数的加成系数。",
                ),
                _make_item(
                    "recent_days",
                    seed_provider_params["recent_days"],
                    "“最近新增”统计窗口（天）。",
                ),
            ],
        ),
        _make_section(
            "打分因子",
            [
                _make_item(
                    "actor_multiplier",
                    seed_weight_params["actor_multiplier"],
                    "演员种子命中的基础权重乘数（会叠加前端偏好与轮换抑制）。",
                ),
                _make_item(
                    "genre_multiplier",
                    seed_weight_params["genre_multiplier"],
                    "类别种子命中的基础权重乘数（会叠加前端偏好与轮换抑制）。",
                ),
                _make_item(
                    "bonus_per_extra",
                    multi_seed_params["bonus_per_extra"],
                    "每多命中一个种子时追加的加分。",
                ),
                _make_item(
                    "search_rank_max_bonus",
                    search_rank_params["max_bonus"],
                    "搜索/列表排序第 1 位的最高加分。",
                ),
                _make_item(
                    "search_rank_decay",
                    search_rank_params["decay"],
                    "排序名次下降时每位扣减的加分。",
                ),
                _make_item(
                    "popularity_views_divisor",
                    popularity_params["views_divisor"],
                    "播放量折算分的分母，越小热度分越敏感。",
                ),
                _make_item(
                    "popularity_likes_divisor",
                    popularity_params["likes_divisor"],
                    "点赞量折算分的分母，越小热度分越敏感。",
                ),
                _make_item(
                    "discovery_hot_board_bonus",
                    discovery_params["hot_board_bonus"],
                    "命中热榜候选时的额外加分。",
                ),
                _make_item(
                    "discovery_latest_updates_bonus",
                    discovery_params["latest_updates_bonus"],
                    "命中最近更新候选时的额外加分。",
                ),
            ],
        ),
        _make_section(
            "新鲜感控制",
            [
                _make_item(
                    "fresh_bonus",
                    novelty_params["fresh_bonus"],
                    "近期历史未出现的候选加分。",
                ),
                _make_item(
                    "repeat_penalty",
                    novelty_params["repeat_penalty"],
                    "近期重复出现时每次的扣分。",
                ),
                _make_item(
                    "max_penalty",
                    novelty_params["max_penalty"],
                    "重复惩罚的最大扣分上限。",
                ),
                _make_item(
                    "jitter_strength",
                    novelty_params["jitter_strength"],
                    "轻微随机扰动强度，用于打散同分结果。",
                ),
            ],
        ),
        _make_section(
            "请求默认值",
            [
                _make_item(
                    "actor_seed_limit",
                    default_request_overrides["actor_seed_limit"],
                    "默认演员种子数量。",
                ),
                _make_item(
                    "genre_seed_limit",
                    default_request_overrides["genre_seed_limit"],
                    "默认类别种子数量。",
                ),
                _make_item(
                    "per_seed_limit",
                    default_request_overrides["per_seed_limit"],
                    "每个种子最多召回候选数量。",
                ),
                _make_item(
                    "discovery_limit",
                    default_request_overrides["discovery_limit"],
                    "热榜/最近更新最多补充的候选数。",
                ),
            ],
        ),
        _make_section(
            "多样性重排",
            [
                _make_item(
                    "diversity_penalty",
                    recommender_kwargs["diversity_penalty"],
                    "候选过于相似时的重排惩罚强度。",
                ),
                _make_item(
                    "actor_diversity_weight",
                    recommender_kwargs["actor_diversity_weight"],
                    "演员维度的去重权重。",
                ),
                _make_item(
                    "genre_diversity_weight",
                    recommender_kwargs["genre_diversity_weight"],
                    "类别维度的去重权重。",
                ),
            ],
        ),
    ]


def build_local_preference_strategy() -> RecommendationStrategy:
    seed_provider_params = {
        "watched_boost": 0.75,
        "favorite_boost": 1.15,
        "recent_boost": 0.9,
        "recent_days": 160,
        "only_interacted": False,
        "fallback_to_all": True,
    }
    seed_weight_params = {"actor_multiplier": 1.0, "genre_multiplier": 1.0}
    multi_seed_params = {"bonus_per_extra": 1.35}
    search_rank_params = {"max_bonus": 1.9, "decay": 0.2}
    popularity_params = {"views_divisor": 560000.0, "likes_divisor": 6200.0}
    discovery_params = {"hot_board_bonus": 1.0, "latest_updates_bonus": 0.78}
    novelty_params = {
        "fresh_bonus": 1.0,
        "repeat_penalty": 0.9,
        "max_penalty": 3.1,
        "jitter_strength": 0.16,
    }
    default_request_overrides = {
        "limit": 12,
        "per_seed_limit": 12,
        "actor_seed_limit": 5,
        "genre_seed_limit": 5,
        "seed_types": ["actor", "genre"],
        "exclude_existing": True,
        "include_hot_board": True,
        "include_latest_updates": True,
        "discovery_limit": 12,
    }
    recommender_kwargs = {
        "diversity_penalty": 0.72,
        "actor_diversity_weight": 1.0,
        "genre_diversity_weight": 0.72,
    }

    return RecommendationStrategy(
        strategy_id="local_preference",
        name="Local Preference",
        description="统一 page lookup + 搜索回退推荐，支持类型/演员/类别偏好参数和种子轮换。",
        supported_recommenders=["jable_page_lookup"],
        seed_provider_builder=lambda: LocalPreferenceSeedProvider(
            watched_boost=seed_provider_params["watched_boost"],
            favorite_boost=seed_provider_params["favorite_boost"],
            recent_boost=seed_provider_params["recent_boost"],
            recent_days=seed_provider_params["recent_days"],
            only_interacted=seed_provider_params["only_interacted"],
            fallback_to_all=seed_provider_params["fallback_to_all"],
        ),
        factor_builders=[
            lambda: SeedWeightFactor(**seed_weight_params),
            lambda: MultiSeedBonusFactor(**multi_seed_params),
            lambda: SearchRankFactor(**search_rank_params),
            lambda: PopularityFactor(
                views_divisor=popularity_params["views_divisor"],
                likes_divisor=popularity_params["likes_divisor"],
            ),
            lambda: DiscoverySourceFactor(**discovery_params),
            lambda: NoveltyFactor(**novelty_params),
        ],
        default_request_overrides=default_request_overrides,
        recommender_kwargs=recommender_kwargs,
        parameter_profile=_build_parameter_profile(
            seed_provider_params=seed_provider_params,
            seed_weight_params=seed_weight_params,
            multi_seed_params=multi_seed_params,
            search_rank_params=search_rank_params,
            popularity_params=popularity_params,
            discovery_params=discovery_params,
            novelty_params=novelty_params,
            default_request_overrides=default_request_overrides,
            recommender_kwargs=recommender_kwargs,
        ),
    )
