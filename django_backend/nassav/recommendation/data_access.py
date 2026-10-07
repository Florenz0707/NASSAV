"""Django adapters load recommendation context in batches and persist snapshots."""

from nassav.models import AVResource

from .contracts import CandidateInventory, RecommendationContextStore
from .entities import RecommendationExecution, RecommendationRequest
from .feedback import recommendation_feedback_repository
from .repository import recommendation_snapshot_repository


class DjangoCandidateInventory(CandidateInventory):
    def existing(self, avids: set[str]) -> set[str]:
        if not avids:
            return set()
        return set(
            AVResource.objects.filter(avid__in=avids).values_list("avid", flat=True)
        )


class DjangoRecommendationContext(RecommendationContextStore):
    def next_random_seed(self) -> int:
        return recommendation_snapshot_repository.next_random_seed()

    def prepare(
        self, request: RecommendationRequest, recommender_id: str, strategy_id: str
    ) -> str:
        from .jobs import history_generation

        request.history_generation = history_generation()
        request_fingerprint = (
            recommendation_snapshot_repository.build_request_fingerprint(
                recommender_id=recommender_id,
                strategy_id=strategy_id,
                request=request,
            )
        )
        if request.avoid_recent_recommendations:
            request.recently_recommended_avids = (
                recommendation_snapshot_repository.get_recent_recommended_avids(
                    recommender_id=recommender_id,
                    strategy_id=strategy_id,
                    request_fingerprint=request_fingerprint,
                    snapshot_limit=request.recent_snapshot_limit,
                    item_limit=request.recent_item_limit,
                )
            )
        request.recent_recommendation_counts = (
            recommendation_snapshot_repository.get_recent_recommendation_counts(
                recommender_id=recommender_id,
                snapshot_limit=max(request.recent_snapshot_limit * 2, 6),
                item_limit=max(request.recent_item_limit * 2, 48),
            )
        )
        request.recent_seed_counts = (
            recommendation_snapshot_repository.get_recent_seed_counts(
                recommender_id=recommender_id,
                snapshot_limit=max(request.recent_snapshot_limit * 3, 8),
                item_limit=max(request.recent_item_limit * 3, 72),
            )
        )
        from .seed_profiles import recommendation_seed_profile_repository

        blocked_name_keys, blocked_source_keys = (
            recommendation_seed_profile_repository.build_blocked_seed_keys()
        )
        request.blocked_seed_name_keys = blocked_name_keys
        request.blocked_seed_source_keys = blocked_source_keys
        request.seed_blacklist_active = bool(blocked_name_keys or blocked_source_keys)
        learning_profile = recommendation_feedback_repository.build_learning_profile()
        request.feedback_avid_scores = learning_profile.avid_scores
        request.feedback_seed_scores = learning_profile.seed_scores
        request.blocked_avid_blocklist = learning_profile.blocked_avids
        request.learned_feedback_count = learning_profile.feedback_count
        request.learned_avid_count = learning_profile.learned_avid_count
        request.learned_seed_count = learning_profile.learned_seed_count
        return request_fingerprint

    def persist(self, execution: RecommendationExecution) -> int | None:
        snapshot = recommendation_snapshot_repository.save_execution(execution)
        return int(snapshot.pk) if snapshot.pk is not None else None
