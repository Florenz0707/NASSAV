from abc import ABC, abstractmethod

from .entities import RecommendationCandidate, RecommendationRequest


class RecommendationFactor(ABC):
    @abstractmethod
    def score(
        self,
        candidate: RecommendationCandidate,
        request: RecommendationRequest,
    ) -> tuple[float, list[str]]:
        raise NotImplementedError


class SeedWeightFactor(RecommendationFactor):
    def score(
        self,
        candidate: RecommendationCandidate,
        request: RecommendationRequest,
    ) -> tuple[float, list[str]]:
        if not candidate.matched_seeds:
            return 0.0, []

        total = round(sum(seed.weight for seed in candidate.matched_seeds), 4)
        reasons = [
            f"命中高频{seed.seed_type}: {seed.value}"
            for seed in sorted(
                candidate.matched_seeds,
                key=lambda item: (-item.weight, item.value),
            )
        ]
        return total, reasons


class MultiSeedBonusFactor(RecommendationFactor):
    def score(
        self,
        candidate: RecommendationCandidate,
        request: RecommendationRequest,
    ) -> tuple[float, list[str]]:
        matched_count = len(candidate.matched_seeds)
        if matched_count <= 1:
            return 0.0, []

        bonus = round((matched_count - 1) * 1.5, 4)
        return bonus, [f"同时命中 {matched_count} 个推荐种子"]


class PopularityFactor(RecommendationFactor):
    def score(
        self,
        candidate: RecommendationCandidate,
        request: RecommendationRequest,
    ) -> tuple[float, list[str]]:
        views = _to_number(candidate.raw_metrics.get("views"))
        likes = _to_number(candidate.raw_metrics.get("likes"))

        score = min(views / 500000.0, 3.0) + min(likes / 5000.0, 2.0)
        if score <= 0:
            return 0.0, []
        return round(score, 4), []


def _to_number(value) -> float:
    if value in (None, ""):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    try:
        text = str(value).replace(",", "").strip()
        return float(text)
    except (TypeError, ValueError):
        return 0.0
