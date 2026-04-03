from django.conf import settings

from nassav.source import Jable

from .entities import RecommendationExecution, RecommendationRequest
from .feedback import recommendation_feedback_repository
from .jable_page_lookup import JablePageLookupRecommender
from .repository import recommendation_snapshot_repository
from .strategies import (
    RecommendationStrategy,
    build_local_preference_strategy,
)


class RecommendationManagerError(Exception):
    pass


class RecommenderManager:
    DEFAULT_RECOMMENDER_ID = "jable_page_lookup"
    DEFAULT_STRATEGY_ID = "local_preference"
    RECOMMENDER_META = {
        "jable_page_lookup": {
            "id": "jable_page_lookup",
            "name": "Jable Page Lookup",
            "description": "优先通过 Jable actor/genre 映射页召回，回退到搜索页。",
        },
    }
    STRATEGY_BUILDERS = {
        "local_preference": build_local_preference_strategy,
    }

    def list_recommenders(self) -> list[dict]:
        items: list[dict] = []
        for recommender_id, meta in self.RECOMMENDER_META.items():
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
        for strategy_id in self.STRATEGY_BUILDERS:
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
        builder = self.STRATEGY_BUILDERS.get(resolved_id)
        if builder is None:
            raise RecommendationManagerError(f"未知推荐策略: {resolved_id}")
        return builder()

    def get_recommender_meta(self, recommender_id: str | None = None) -> dict:
        resolved_id = recommender_id or self.DEFAULT_RECOMMENDER_ID
        meta = self.RECOMMENDER_META.get(resolved_id)
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

        recommender_meta = self.get_recommender_meta(resolved_recommender_id)
        strategy = self.get_strategy(resolved_strategy_id)
        self._validate_support(
            recommender_id=resolved_recommender_id,
            strategy=strategy,
        )

        recommendation_request = self.build_request(
            strategy=strategy,
            request_params=request_params or {},
        )
        request_fingerprint = (
            recommendation_snapshot_repository.build_request_fingerprint(
                recommender_id=resolved_recommender_id,
                strategy_id=resolved_strategy_id,
                request=recommendation_request,
            )
        )
        if recommendation_request.avoid_recent_recommendations:
            recommendation_request.recently_recommended_avids = (
                recommendation_snapshot_repository.get_recent_recommended_avids(
                    recommender_id=resolved_recommender_id,
                    strategy_id=resolved_strategy_id,
                    request_fingerprint=request_fingerprint,
                    snapshot_limit=recommendation_request.recent_snapshot_limit,
                    item_limit=recommendation_request.recent_item_limit,
                )
            )
        recommendation_request.recent_recommendation_counts = (
            recommendation_snapshot_repository.get_recent_recommendation_counts(
                recommender_id=resolved_recommender_id,
                snapshot_limit=max(recommendation_request.recent_snapshot_limit * 2, 6),
                item_limit=max(recommendation_request.recent_item_limit * 2, 48),
            )
        )
        recommendation_request.recent_seed_counts = (
            recommendation_snapshot_repository.get_recent_seed_counts(
                recommender_id=resolved_recommender_id,
                snapshot_limit=max(recommendation_request.recent_snapshot_limit * 3, 8),
                item_limit=max(recommendation_request.recent_item_limit * 3, 72),
            )
        )
        learning_profile = recommendation_feedback_repository.build_learning_profile()
        recommendation_request.feedback_avid_scores = learning_profile.avid_scores
        recommendation_request.feedback_seed_scores = learning_profile.seed_scores
        recommendation_request.blocked_feedback_avids = learning_profile.blocked_avids
        recommendation_request.learned_feedback_count = learning_profile.feedback_count
        recommendation_request.learned_avid_count = learning_profile.learned_avid_count
        recommendation_request.learned_seed_count = learning_profile.learned_seed_count
        recommender = self.build_recommender(
            recommender_id=resolved_recommender_id,
            strategy=strategy,
        )
        run = recommender.recommend(recommendation_request)
        filtered_history_count = sum(
            1
            for avid in recommendation_request.recently_recommended_avids
            if all(item.avid != avid for item in run.items)
        )
        execution = RecommendationExecution(
            recommender_id=resolved_recommender_id,
            strategy_id=resolved_strategy_id,
            request=recommendation_request,
            run=run,
            recommender_meta=recommender_meta,
            strategy_meta=strategy.to_dict(),
            request_fingerprint=request_fingerprint,
            filtered_history_count=filtered_history_count,
        )
        snapshot = recommendation_snapshot_repository.save_execution(execution)
        execution.snapshot_id = int(snapshot.pk) if snapshot.pk is not None else None
        for item in execution.run.items:
            item.snapshot_id = execution.snapshot_id
        return execution

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
            limit=int(payload.get("limit", 12)),
            per_seed_limit=int(payload.get("per_seed_limit", 12)),
            actor_seed_limit=int(payload.get("actor_seed_limit", 5)),
            genre_seed_limit=int(payload.get("genre_seed_limit", 5)),
            seed_types=list(payload.get("seed_types", ["actor", "genre"])),
            exclude_existing=bool(payload.get("exclude_existing", True)),
            random_seed=int(
                payload.get(
                    "random_seed",
                    recommendation_snapshot_repository.next_random_seed(),
                )
            ),
            avoid_recent_recommendations=bool(
                payload.get("avoid_recent_recommendations", True)
            ),
            recent_snapshot_limit=int(payload.get("recent_snapshot_limit", 3)),
            recent_item_limit=int(payload.get("recent_item_limit", 36)),
            include_hot_board=bool(payload.get("include_hot_board", True)),
            include_latest_updates=bool(payload.get("include_latest_updates", True)),
            discovery_limit=int(payload.get("discovery_limit", 12)),
            type_preference=str(payload.get("type_preference", "balanced")),
            actor_preference=str(payload.get("actor_preference", "balanced")),
            genre_preference=str(payload.get("genre_preference", "balanced")),
        )

    def build_recommender(
        self,
        recommender_id: str,
        strategy: RecommendationStrategy,
    ):
        if recommender_id == "jable_page_lookup":
            return self._build_jable_page_lookup_recommender(strategy)
        raise RecommendationManagerError(f"未知推荐器: {recommender_id}")

    def _validate_support(
        self,
        recommender_id: str,
        strategy: RecommendationStrategy,
    ) -> None:
        if recommender_id not in strategy.supported_recommenders:
            raise RecommendationManagerError(
                f"推荐策略 {strategy.strategy_id} 不支持推荐器 {recommender_id}"
            )

    def _build_jable_page_lookup_recommender(
        self,
        strategy: RecommendationStrategy,
    ) -> JablePageLookupRecommender:
        proxy = settings.PROXY_URL if settings.PROXY_ENABLED else None
        return JablePageLookupRecommender(
            jable=Jable(proxy=proxy),
            seed_provider=strategy.seed_provider_builder(),
            factors=[builder() for builder in strategy.factor_builders],
            **strategy.recommender_kwargs,
        )


recommender_manager = RecommenderManager()
