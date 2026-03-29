from abc import ABC, abstractmethod
from hashlib import blake2b

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


class NoveltyFactor(RecommendationFactor):
    def __init__(
        self,
        *,
        fresh_bonus: float = 0.8,
        repeat_penalty: float = 0.6,
        max_penalty: float = 2.4,
        jitter_strength: float = 0.2,
    ):
        self.fresh_bonus = fresh_bonus
        self.repeat_penalty = repeat_penalty
        self.max_penalty = max_penalty
        self.jitter_strength = jitter_strength

    def score(
        self,
        candidate: RecommendationCandidate,
        request: RecommendationRequest,
    ) -> tuple[float, list[str]]:
        history_count = request.recent_recommendation_counts.get(candidate.avid, 0)
        score = 0.0
        reasons: list[str] = []

        if history_count <= 0:
            score += self.fresh_bonus
            if self.fresh_bonus > 0:
                reasons.append("近期推荐历史中未出现，提升新颖度")
        else:
            penalty = min(history_count * self.repeat_penalty, self.max_penalty)
            score -= penalty
            reasons.append(f"近期已在 {history_count} 次推荐中出现，降低新颖度")

        if self.jitter_strength > 0:
            score += self._jitter(candidate, request)

        if score == 0 and not reasons:
            return 0.0, []
        return round(score, 4), reasons

    def _jitter(
        self,
        candidate: RecommendationCandidate,
        request: RecommendationRequest,
    ) -> float:
        digest = blake2b(
            f"{request.random_seed}:{candidate.avid}:novelty".encode("utf-8"),
            digest_size=8,
        ).digest()
        value = int.from_bytes(digest, "big") / float(2**64 - 1)
        centered = (value * 2.0) - 1.0
        return centered * self.jitter_strength


class FeedbackSignalFactor(RecommendationFactor):
    def __init__(
        self,
        *,
        avid_weight: float = 2.4,
        seed_weight: float = 1.6,
        max_bonus: float = 3.0,
        max_penalty: float = 3.0,
    ):
        self.avid_weight = avid_weight
        self.seed_weight = seed_weight
        self.max_bonus = max_bonus
        self.max_penalty = max_penalty

    def score(
        self,
        candidate: RecommendationCandidate,
        request: RecommendationRequest,
    ) -> tuple[float, list[str]]:
        total_score = 0.0
        reasons: list[str] = []

        avid_signal = request.feedback_avid_scores.get(candidate.avid, 0.0)
        if avid_signal != 0:
            total_score += avid_signal * self.avid_weight
            if avid_signal > 0:
                reasons.append("历史反馈偏好该资源，提升排序")
            else:
                reasons.append("历史反馈对该资源偏弱，降低排序")

        seed_hits: list[tuple[str, float]] = []
        for seed in candidate.matched_seeds:
            key = f"{seed.seed_type}:{seed.value}"
            signal = request.feedback_seed_scores.get(key, 0.0)
            if signal == 0:
                continue
            seed_hits.append((seed.value, signal))

        if seed_hits:
            average_seed_signal = sum(signal for _, signal in seed_hits) / len(
                seed_hits
            )
            total_score += average_seed_signal * self.seed_weight
            seed_names = " / ".join(name for name, _ in seed_hits[:2])
            if average_seed_signal > 0:
                reasons.append(f"历史反馈偏好相关种子: {seed_names}")
            else:
                reasons.append(f"历史反馈降低相关种子权重: {seed_names}")

        if total_score == 0 and not reasons:
            return 0.0, []

        total_score = max(min(total_score, self.max_bonus), -self.max_penalty)
        return round(total_score, 4), reasons


class DiscoverySourceFactor(RecommendationFactor):
    def __init__(
        self,
        *,
        hot_board_bonus: float = 1.0,
        latest_updates_bonus: float = 0.7,
    ):
        self.hot_board_bonus = hot_board_bonus
        self.latest_updates_bonus = latest_updates_bonus

    def score(
        self,
        candidate: RecommendationCandidate,
        request: RecommendationRequest,
    ) -> tuple[float, list[str]]:
        _ = request
        discovery_sources = list(candidate.raw_metrics.get("discovery_sources") or [])
        if not discovery_sources:
            return 0.0, []

        score = 0.0
        reasons: list[str] = []
        if "hot_board" in discovery_sources and self.hot_board_bonus > 0:
            score += self.hot_board_bonus
            reasons.append("命中 Jable 热榜候选")
        if "latest_updates" in discovery_sources and self.latest_updates_bonus > 0:
            score += self.latest_updates_bonus
            reasons.append("命中 Jable 最近更新候选")

        if score <= 0:
            return 0.0, []
        return round(score, 4), reasons


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
