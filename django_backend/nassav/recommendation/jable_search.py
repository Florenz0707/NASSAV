from loguru import logger

from nassav.source import Jable

from .base import AbstractRecommender
from .entities import RecommendationCandidate, RecommendationRequest, RecommendationSeed
from .seeds import SeedProvider


class JableSearchRecommender(AbstractRecommender):
    def __init__(
        self,
        jable: Jable,
        seed_provider: SeedProvider,
        factors=None,
        *,
        diversity_penalty: float = 0.0,
        actor_diversity_weight: float = 1.0,
        genre_diversity_weight: float = 0.5,
    ):
        super().__init__(factors=factors)
        self.jable = jable
        self.seed_provider = seed_provider
        self.diversity_penalty = diversity_penalty
        self.actor_diversity_weight = actor_diversity_weight
        self.genre_diversity_weight = genre_diversity_weight

    def build_seeds(self, request: RecommendationRequest) -> list[RecommendationSeed]:
        return self.seed_provider.get_seeds(request)

    def recall_candidates(
        self,
        seeds: list[RecommendationSeed],
        request: RecommendationRequest,
    ) -> list[RecommendationCandidate]:
        merged: dict[str, RecommendationCandidate] = {}
        for seed in seeds:
            candidates = self.recall_by_seed(seed, request)
            for candidate in candidates:
                existing = merged.get(candidate.avid)
                if existing is None:
                    merged[candidate.avid] = candidate
                    continue

                for matched_seed in candidate.matched_seeds:
                    existing.add_seed(matched_seed)
                existing.raw_metrics = self._merge_metrics(
                    existing.raw_metrics,
                    candidate.raw_metrics,
                )
                if not existing.title and candidate.title:
                    existing.title = candidate.title
                if not existing.detail_url and candidate.detail_url:
                    existing.detail_url = candidate.detail_url
                if not existing.cover_url and candidate.cover_url:
                    existing.cover_url = candidate.cover_url
                if candidate.search_rank is not None:
                    if existing.search_rank is None:
                        existing.search_rank = candidate.search_rank
                    else:
                        existing.search_rank = min(
                            existing.search_rank,
                            candidate.search_rank,
                        )

        return list(merged.values())

    def recall_by_seed(
        self,
        seed: RecommendationSeed,
        request: RecommendationRequest,
    ) -> list[RecommendationCandidate]:
        raw_results = self.jable.search(seed.value, page=1)
        if request.per_seed_limit > 0:
            raw_results = raw_results[: request.per_seed_limit]

        candidates: list[RecommendationCandidate] = []
        for index, item in enumerate(raw_results, start=1):
            avid = str(item.get("avid", "")).strip().upper()
            if not avid:
                logger.debug(f"[JableSearchRecommender] 跳过缺少 avid 的候选: {item}")
                continue

            candidate = RecommendationCandidate(
                avid=avid,
                title=str(item.get("title", "")).strip(),
                detail_url=str(item.get("detail_url", "")).strip(),
                cover_url=str(item.get("cover_url", "")).strip(),
                source=str(item.get("source", "Jable")).strip() or "Jable",
                search_rank=index,
                raw_metrics=dict(item.get("metrics") or {}),
            )
            candidate.add_seed(seed)
            candidates.append(candidate)

        return candidates

    def rerank_candidates(
        self,
        ranked_candidates: list[RecommendationCandidate],
        request: RecommendationRequest,
    ) -> list[RecommendationCandidate]:
        _ = request
        if self.diversity_penalty <= 0 or len(ranked_candidates) <= 1:
            return ranked_candidates

        remaining = list(ranked_candidates)
        selected: list[RecommendationCandidate] = []
        seen_seed_counts: dict[str, int] = {}

        while remaining:
            best_index = 0
            best_score = None
            for index, candidate in enumerate(remaining):
                adjusted_score = candidate.total_score - self._diversity_penalty(
                    candidate, seen_seed_counts
                )
                if best_score is None or adjusted_score > best_score:
                    best_score = adjusted_score
                    best_index = index

            chosen = remaining.pop(best_index)
            selected.append(chosen)
            for key in self._seed_keys(chosen):
                seen_seed_counts[key] = seen_seed_counts.get(key, 0) + 1

        return selected

    def _diversity_penalty(
        self,
        candidate: RecommendationCandidate,
        seen_seed_counts: dict[str, int],
    ) -> float:
        penalty = 0.0
        for key in self._seed_keys(candidate):
            repeat_count = seen_seed_counts.get(key, 0)
            if repeat_count <= 0:
                continue
            penalty += (
                repeat_count * self.diversity_penalty * self._seed_penalty_weight(key)
            )
        return penalty

    def _seed_keys(self, candidate: RecommendationCandidate) -> list[str]:
        keys = []
        for seed in candidate.matched_seeds:
            keys.append(f"{seed.seed_type}:{seed.value}")
        return keys

    def _seed_penalty_weight(self, key: str) -> float:
        if key.startswith("actor:"):
            return self.actor_diversity_weight
        if key.startswith("genre:"):
            return self.genre_diversity_weight
        return 1.0

    def _merge_metrics(self, base: dict, extra: dict) -> dict:
        merged = dict(base or {})
        for key, value in (extra or {}).items():
            if key not in merged or not merged[key]:
                merged[key] = value
        return merged
