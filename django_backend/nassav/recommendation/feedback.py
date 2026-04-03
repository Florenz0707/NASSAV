from dataclasses import dataclass, field

from django.db import transaction

from nassav.models import (
    RecommendationAvidBlocklist,
    RecommendationFeedback,
    RecommendationItem,
)

from .seed_profiles import recommendation_seed_profile_repository


class RecommendationFeedbackError(Exception):
    pass


@dataclass
class RecommendationLearningProfile:
    avid_scores: dict[str, float] = field(default_factory=dict)
    seed_scores: dict[str, float] = field(default_factory=dict)
    blocked_avids: set[str] = field(default_factory=set)
    feedback_count: int = 0

    @property
    def learned_avid_count(self) -> int:
        return len(self.avid_scores)

    @property
    def learned_seed_count(self) -> int:
        return len(self.seed_scores)


class RecommendationFeedbackRepository:
    VALID_FEEDBACKS = {"dislike"}

    @transaction.atomic
    def record_feedback(
        self,
        *,
        snapshot_id: int,
        avid: str,
        feedback: str,
    ) -> RecommendationFeedback | None:
        normalized_feedback = str(feedback or "").strip().lower()
        if normalized_feedback not in self.VALID_FEEDBACKS:
            raise RecommendationFeedbackError(f"未知反馈类型: {feedback}")

        normalized_avid = str(avid or "").strip().upper()
        if not normalized_avid:
            raise RecommendationFeedbackError("avid 参数缺失")

        item = (
            RecommendationItem.objects.select_related("snapshot")
            .filter(snapshot_id=snapshot_id, avid=normalized_avid)
            .first()
        )
        if item is None:
            raise RecommendationFeedbackError("推荐项不存在，无法记录反馈")

        feedback_obj, _ = RecommendationFeedback.objects.update_or_create(
            item=item,
            defaults={
                "avid": normalized_avid,
                "feedback": normalized_feedback,
            },
        )
        RecommendationAvidBlocklist.objects.update_or_create(
            avid=normalized_avid,
            defaults={
                "source": "user_feedback",
                "reason": "dislike",
            },
        )
        recommendation_seed_profile_repository.increment_dislike_counts_for_item(item)
        return feedback_obj

    def build_learning_profile(self) -> RecommendationLearningProfile:
        blocked_avids = set(
            RecommendationAvidBlocklist.objects.values_list("avid", flat=True)
        )
        return RecommendationLearningProfile(
            seed_scores=recommendation_seed_profile_repository.build_seed_score_map(),
            blocked_avids=blocked_avids,
            feedback_count=RecommendationFeedback.objects.filter(
                feedback="dislike"
            ).count(),
        )


recommendation_feedback_repository = RecommendationFeedbackRepository()
