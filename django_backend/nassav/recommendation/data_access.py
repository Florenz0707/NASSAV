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
    def __init__(self, user_id=None):
        self.user_id = user_id
        self.snapshots = (
            recommendation_snapshot_repository
            if user_id is None
            else recommendation_snapshot_repository.for_user(user_id)
        )
        self.feedback = (
            recommendation_feedback_repository
            if user_id is None
            else recommendation_feedback_repository.for_user(user_id)
        )

    def next_random_seed(self) -> int:
        return self.snapshots.next_random_seed()

    def prepare(
        self, request: RecommendationRequest, recommender_id: str, strategy_id: str
    ) -> str:
        from .jobs import history_generation

        request.user_id = self.user_id
        request.history_generation = history_generation(self.user_id)
        request_fingerprint = self.snapshots.build_request_fingerprint(
            recommender_id=recommender_id,
            strategy_id=strategy_id,
            request=request,
        )
        if request.avoid_recent_recommendations:
            request.recently_recommended_avids = (
                self.snapshots.get_recent_recommended_avids(
                    recommender_id=recommender_id,
                    strategy_id=strategy_id,
                    request_fingerprint=request_fingerprint,
                    snapshot_limit=request.recent_snapshot_limit,
                    item_limit=request.recent_item_limit,
                )
            )
        request.recent_recommendation_counts = (
            self.snapshots.get_recent_recommendation_counts(
                recommender_id=recommender_id,
                snapshot_limit=max(request.recent_snapshot_limit * 2, 6),
                item_limit=max(request.recent_item_limit * 2, 48),
            )
        )
        request.recent_seed_counts = self.snapshots.get_recent_seed_counts(
            recommender_id=recommender_id,
            snapshot_limit=max(request.recent_snapshot_limit * 3, 8),
            item_limit=max(request.recent_item_limit * 3, 72),
        )
        from .seed_profiles import recommendation_seed_profile_repository

        blocked_name_keys, blocked_source_keys = (
            recommendation_seed_profile_repository.for_user(
                self.user_id
            ).build_blocked_seed_keys()
        )
        request.blocked_seed_name_keys = blocked_name_keys
        request.blocked_seed_source_keys = blocked_source_keys
        request.seed_blacklist_active = bool(blocked_name_keys or blocked_source_keys)
        learning_profile = self.feedback.build_learning_profile()
        request.feedback_avid_scores = learning_profile.avid_scores
        request.feedback_seed_scores = learning_profile.seed_scores
        request.blocked_avid_blocklist = learning_profile.blocked_avids
        request.learned_feedback_count = learning_profile.feedback_count
        request.learned_avid_count = learning_profile.learned_avid_count
        request.learned_seed_count = learning_profile.learned_seed_count
        return request_fingerprint

    def persist(self, execution: RecommendationExecution) -> int | None:
        snapshot = self.snapshots.save_execution(execution)
        return int(snapshot.pk) if snapshot.pk is not None else None
