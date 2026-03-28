from loguru import logger

from nassav.source import Jable

from .base import AbstractRecommender
from .entities import RecommendationCandidate, RecommendationRequest, RecommendationSeed
from .seeds import SeedProvider


class JableSearchRecommender(AbstractRecommender):
    def __init__(self, jable: Jable, seed_provider: SeedProvider, factors=None):
        super().__init__(factors=factors)
        self.jable = jable
        self.seed_provider = seed_provider

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
        for item in raw_results:
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
                raw_metrics=dict(item.get("metrics") or {}),
            )
            candidate.add_seed(seed)
            candidates.append(candidate)

        return candidates

    def _merge_metrics(self, base: dict, extra: dict) -> dict:
        merged = dict(base or {})
        for key, value in (extra or {}).items():
            if key not in merged or not merged[key]:
                merged[key] = value
        return merged
