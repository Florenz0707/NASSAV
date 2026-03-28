from django.conf import settings

from nassav.source import Jable

from .entities import RecommendationExecution, RecommendationRequest
from .jable_search import JableSearchRecommender
from .strategies import RecommendationStrategy, build_local_demo_strategy


class RecommendationManagerError(Exception):
    pass


class RecommenderManager:
    DEFAULT_RECOMMENDER_ID = "jable_search"
    DEFAULT_STRATEGY_ID = "local_demo"

    def __init__(self):
        self.recommender_builders = {
            "jable_search": self._build_jable_search_recommender,
        }
        self.recommender_meta = {
            "jable_search": {
                "id": "jable_search",
                "name": "Jable Search",
                "description": "通过 Jable 搜索页召回候选资源。",
            }
        }
        self.strategy_builders = {
            "local_demo": build_local_demo_strategy,
        }

    def list_recommenders(self) -> list[dict]:
        items: list[dict] = []
        for recommender_id, meta in self.recommender_meta.items():
            items.append(
                {
                    **meta,
                    "strategies": [
                        strategy["id"]
                        for strategy in self.list_strategies(recommender_id)
                    ],
                }
            )
        return items

    def list_strategies(self, recommender_id: str | None = None) -> list[dict]:
        items: list[dict] = []
        for strategy_id in self.strategy_builders:
            strategy = self.get_strategy(strategy_id)
            if (
                recommender_id is not None
                and recommender_id not in strategy.supported_recommenders
            ):
                continue
            items.append(strategy.to_dict())
        return items

    def get_strategy(self, strategy_id: str | None = None) -> RecommendationStrategy:
        resolved_id = strategy_id or self.DEFAULT_STRATEGY_ID
        builder = self.strategy_builders.get(resolved_id)
        if builder is None:
            raise RecommendationManagerError(f"未知推荐策略: {resolved_id}")
        return builder()

    def get_recommender_meta(self, recommender_id: str | None = None) -> dict:
        resolved_id = recommender_id or self.DEFAULT_RECOMMENDER_ID
        meta = self.recommender_meta.get(resolved_id)
        if meta is None:
            raise RecommendationManagerError(f"未知推荐器: {resolved_id}")
        return meta

    def get_options(self) -> dict:
        return {
            "defaults": {
                "recommender": self.DEFAULT_RECOMMENDER_ID,
                "strategy": self.DEFAULT_STRATEGY_ID,
            },
            "recommenders": self.list_recommenders(),
            "strategies": self.list_strategies(),
        }

    def recommend(
        self,
        recommender_id: str | None = None,
        strategy_id: str | None = None,
        request_params: dict | None = None,
    ) -> RecommendationExecution:
        resolved_recommender_id = recommender_id or self.DEFAULT_RECOMMENDER_ID
        resolved_strategy_id = strategy_id or self.DEFAULT_STRATEGY_ID

        strategy = self.get_strategy(resolved_strategy_id)
        self.get_recommender_meta(resolved_recommender_id)
        self._validate_support(
            recommender_id=resolved_recommender_id,
            strategy=strategy,
        )

        recommendation_request = self.build_request(
            strategy=strategy,
            request_params=request_params or {},
        )
        recommender = self.build_recommender(
            recommender_id=resolved_recommender_id,
            strategy=strategy,
        )
        run = recommender.recommend(recommendation_request)
        return RecommendationExecution(
            recommender_id=resolved_recommender_id,
            strategy_id=resolved_strategy_id,
            request=recommendation_request,
            run=run,
        )

    def build_request(
        self,
        strategy: RecommendationStrategy,
        request_params: dict,
    ) -> RecommendationRequest:
        payload = dict(strategy.default_request_overrides)
        payload.update(
            {key: value for key, value in request_params.items() if value is not None}
        )
        return RecommendationRequest(
            limit=int(payload.get("limit", 24)),
            per_seed_limit=int(payload.get("per_seed_limit", 12)),
            actor_seed_limit=int(payload.get("actor_seed_limit", 5)),
            genre_seed_limit=int(payload.get("genre_seed_limit", 5)),
            seed_types=list(payload.get("seed_types", ["actor", "genre"])),
        )

    def build_recommender(
        self,
        recommender_id: str,
        strategy: RecommendationStrategy,
    ):
        builder = self.recommender_builders.get(recommender_id)
        if builder is None:
            raise RecommendationManagerError(f"未知推荐器: {recommender_id}")
        return builder(strategy)

    def _validate_support(
        self,
        recommender_id: str,
        strategy: RecommendationStrategy,
    ) -> None:
        if recommender_id not in strategy.supported_recommenders:
            raise RecommendationManagerError(
                f"推荐策略 {strategy.strategy_id} 不支持推荐器 {recommender_id}"
            )

    def _build_jable_search_recommender(
        self,
        strategy: RecommendationStrategy,
    ) -> JableSearchRecommender:
        proxy = settings.PROXY_URL if settings.PROXY_ENABLED else None
        return JableSearchRecommender(
            jable=Jable(proxy=proxy),
            seed_provider=strategy.seed_provider_builder(),
            factors=[builder() for builder in strategy.factor_builders],
        )


recommender_manager = RecommenderManager()
