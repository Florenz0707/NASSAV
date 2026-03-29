from dataclasses import dataclass, field

from django.db import transaction

from nassav.models import RecommendationFeedback, RecommendationItem


class RecommendationFeedbackError(Exception):
    pass


@dataclass
class RecommendationLearningProfile:
    avid_scores: dict[str, float] = field(default_factory=dict)
    seed_scores: dict[str, float] = field(default_factory=dict)
    feedback_count: int = 0

    @property
    def learned_avid_count(self) -> int:
        return len(self.avid_scores)

    @property
    def learned_seed_count(self) -> int:
        return len(self.seed_scores)


class RecommendationFeedbackRepository:
    VALID_FEEDBACKS = {"like", "dislike", "clear"}
    POSITIVE_FEEDBACKS = {"like"}
    NEGATIVE_FEEDBACKS = {"dislike"}

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

        if normalized_feedback == "clear":
            RecommendationFeedback.objects.filter(item=item).delete()
            return None

        feedback_obj, _ = RecommendationFeedback.objects.update_or_create(
            item=item,
            defaults={
                "avid": normalized_avid,
                "feedback": normalized_feedback,
            },
        )
        return feedback_obj

    def build_learning_profile(self) -> RecommendationLearningProfile:
        feedbacks = RecommendationFeedback.objects.select_related("item").all()
        if not feedbacks:
            return RecommendationLearningProfile()

        avid_votes: dict[str, list[int]] = {}
        seed_votes: dict[str, list[int]] = {}

        for feedback in feedbacks:
            avid_votes.setdefault(feedback.avid, []).append(feedback.feedback_value)

            for seed in feedback.item.matched_seeds or []:
                seed_type = str(seed.get("seed_type", "")).strip()
                seed_value = str(seed.get("value", "")).strip()
                if not seed_type or not seed_value:
                    continue
                key = f"{seed_type}:{seed_value}"
                seed_votes.setdefault(key, []).append(feedback.feedback_value)

        return RecommendationLearningProfile(
            avid_scores={
                avid: self._build_signal(votes)
                for avid, votes in avid_votes.items()
                if votes
            },
            seed_scores={
                seed_key: self._build_signal(votes)
                for seed_key, votes in seed_votes.items()
                if votes
            },
            feedback_count=feedbacks.count(),
        )

    def _build_signal(self, votes: list[int]) -> float:
        total = len(votes)
        if total <= 0:
            return 0.0

        positive_count = sum(1 for value in votes if value > 0)
        negative_count = sum(1 for value in votes if value < 0)
        if positive_count == 0 and negative_count == 0:
            return 0.0

        normalized = (positive_count - negative_count) / float(total)
        confidence = min(total / 3.0, 1.0)
        return round(normalized * confidence, 4)


recommendation_feedback_repository = RecommendationFeedbackRepository()
