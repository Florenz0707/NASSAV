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
    def __init__(
        self,
        *,
        actor_multiplier: float = 1.0,
        genre_multiplier: float = 0.7,
    ):
        self.actor_multiplier = actor_multiplier
        self.genre_multiplier = genre_multiplier

    def score(
        self,
        candidate: RecommendationCandidate,
        request: RecommendationRequest,
    ) -> tuple[float, list[str]]:
        if not candidate.matched_seeds:
            return 0.0, []

        total = 0.0
        reasons: list[str] = []
        for seed in sorted(
            candidate.matched_seeds,
            key=lambda item: (-item.weight, item.value),
        ):
            multiplier = self._get_multiplier(seed.seed_type)
            total += seed.weight * multiplier
            reasons.append(
                f"命中高频{seed.seed_type}: {seed.value} (x{multiplier:.2f})"
            )

        return round(total, 4), reasons

    def _get_multiplier(self, seed_type: str) -> float:
        if seed_type == "actor":
            return self.actor_multiplier
        if seed_type == "genre":
            return self.genre_multiplier
        return 1.0


class MultiSeedBonusFactor(RecommendationFactor):
    def __init__(self, *, bonus_per_extra: float = 1.5):
        self.bonus_per_extra = bonus_per_extra

    def score(
        self,
        candidate: RecommendationCandidate,
        request: RecommendationRequest,
    ) -> tuple[float, list[str]]:
        matched_count = len(candidate.matched_seeds)
        if matched_count <= 1:
            return 0.0, []

        bonus = round((matched_count - 1) * self.bonus_per_extra, 4)
        return bonus, [f"同时命中 {matched_count} 个推荐种子"]


class SearchRankFactor(RecommendationFactor):
    def __init__(
        self,
        *,
        max_bonus: float = 2.0,
        decay: float = 0.2,
    ):
        self.max_bonus = max_bonus
        self.decay = decay

    def score(
        self,
        candidate: RecommendationCandidate,
        request: RecommendationRequest,
    ) -> tuple[float, list[str]]:
        if not candidate.search_rank or candidate.search_rank <= 0:
            return 0.0, []

        score = max(self.max_bonus - (candidate.search_rank - 1) * self.decay, 0.0)
        if score <= 0:
            return 0.0, []

        return round(score, 4), [f"搜索结果排序靠前: 第 {candidate.search_rank} 位"]


class PopularityFactor(RecommendationFactor):
    def __init__(
        self,
        *,
        views_divisor: float = 500000.0,
        views_cap: float = 3.0,
        likes_divisor: float = 5000.0,
        likes_cap: float = 2.0,
    ):
        self.views_divisor = views_divisor
        self.views_cap = views_cap
        self.likes_divisor = likes_divisor
        self.likes_cap = likes_cap

    def score(
        self,
        candidate: RecommendationCandidate,
        request: RecommendationRequest,
    ) -> tuple[float, list[str]]:
        views = _to_number(candidate.raw_metrics.get("views"))
        likes = _to_number(candidate.raw_metrics.get("likes"))

        score = min(views / self.views_divisor, self.views_cap) + min(
            likes / self.likes_divisor, self.likes_cap
        )
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
