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
    def __init__(self, user_id=None):
        self.user_id = user_id

    def for_user(self, user_id):
        return type(self)(user_id=user_id)

    @property
    def items(self):
        return RecommendationItem.objects.filter(snapshot__owner_id=self.user_id)

    @property
    def feedbacks(self):
        return RecommendationFeedback.objects.filter(
            item__snapshot__owner_id=self.user_id
        )

    @property
    def blocks(self):
        return RecommendationAvidBlocklist.objects.filter(owner_id=self.user_id)

    @property
    def seed_profiles(self):
        return (
            recommendation_seed_profile_repository
            if self.user_id is None
            else recommendation_seed_profile_repository.for_user(self.user_id)
        )

    VALID_FEEDBACKS = {"like", "dislike", "clear"}

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

        from .jobs import lock_history

        lock_history(self.user_id)
        item = (
            self.items.select_related("snapshot")
            .filter(snapshot_id=snapshot_id, avid=normalized_avid)
            .first()
        )
        if item is None:
            raise RecommendationFeedbackError("推荐项不存在，无法记录反馈")

        existing_feedback = (
            self.feedbacks.filter(item=item).values_list("feedback", flat=True).first()
        )
        if normalized_feedback == "clear":
            self.feedbacks.filter(item=item).delete()
            self.seed_profiles.adjust_feedback_counts_for_item(
                item,
                old_feedback=existing_feedback or "",
                new_feedback="",
            )
            return None

        feedback_obj, _ = self.feedbacks.update_or_create(
            item=item,
            defaults={
                "avid": normalized_avid,
                "feedback": normalized_feedback,
            },
        )
        self.seed_profiles.adjust_feedback_counts_for_item(
            item,
            old_feedback=existing_feedback or "",
            new_feedback=normalized_feedback,
        )
        return feedback_obj

    def build_learning_profile(self) -> RecommendationLearningProfile:
        blocked_avids = set(self.blocks.values_list("avid", flat=True))
        return RecommendationLearningProfile(
            seed_scores=self.seed_profiles.build_seed_score_map(),
            blocked_avids=blocked_avids,
            feedback_count=self.feedbacks.count(),
        )


recommendation_feedback_repository = RecommendationFeedbackRepository()
