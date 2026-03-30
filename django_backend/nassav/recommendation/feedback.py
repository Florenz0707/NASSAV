from dataclasses import dataclass, field

from django.db import transaction

from nassav.models import RecommendationFeedback, RecommendationItem


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
        return feedback_obj

    def build_learning_profile(self) -> RecommendationLearningProfile:
        feedbacks = RecommendationFeedback.objects.select_related("item").filter(
            feedback="dislike"
        )
        if not feedbacks:
            return RecommendationLearningProfile()

        return RecommendationLearningProfile(
            blocked_avids=set(feedbacks.values_list("avid", flat=True)),
            feedback_count=feedbacks.count(),
        )


recommendation_feedback_repository = RecommendationFeedbackRepository()
