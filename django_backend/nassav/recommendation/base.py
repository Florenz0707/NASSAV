from abc import ABC, abstractmethod

from nassav.models import AVResource

from .entities import RecommendationCandidate, RecommendationRequest, RecommendationRun
from .factors import RecommendationFactor


class AbstractRecommender(ABC):
    def __init__(self, factors: list[RecommendationFactor] | None = None):
        self.factors = factors or []

    def recommend(self, request: RecommendationRequest) -> RecommendationRun:
        seeds = self.build_seeds(request)
        candidates = self.recall_candidates(seeds, request)
        candidates = self.filter_existing_resources(candidates)
        candidates = self.enrich_candidates(candidates, request)
        candidates = self.score_candidates(candidates, request)
        items = self.rank_and_trim(candidates, request)
        return RecommendationRun(seeds=seeds, items=items)

    @abstractmethod
    def build_seeds(self, request: RecommendationRequest):
        raise NotImplementedError

    @abstractmethod
    def recall_candidates(self, seeds, request: RecommendationRequest):
        raise NotImplementedError

    def filter_existing_resources(
        self,
        candidates: list[RecommendationCandidate],
    ) -> list[RecommendationCandidate]:
        if not candidates:
            return candidates

        existing_avids = set(
            AVResource.objects.filter(
                avid__in=[candidate.avid for candidate in candidates]
            ).values_list("avid", flat=True)
        )
        return [
            candidate
            for candidate in candidates
            if candidate.avid not in existing_avids
        ]

    def enrich_candidates(
        self,
        candidates: list[RecommendationCandidate],
        request: RecommendationRequest,
    ) -> list[RecommendationCandidate]:
        return candidates

    def score_candidates(
        self,
        candidates: list[RecommendationCandidate],
        request: RecommendationRequest,
    ) -> list[RecommendationCandidate]:
        for candidate in candidates:
            total_score = 0.0
            score_breakdown: list[dict] = []
            for factor in self.factors:
                score, reasons = factor.score(candidate, request)
                if score == 0 and not reasons:
                    continue
                total_score += score
                score_breakdown.append(
                    {
                        "factor": factor.__class__.__name__,
                        "score": round(score, 4),
                        "reasons": reasons,
                    }
                )

            candidate.total_score = round(total_score, 4)
            candidate.score_breakdown = score_breakdown
        return candidates

    def rank_and_trim(
        self,
        candidates: list[RecommendationCandidate],
        request: RecommendationRequest,
    ) -> list[RecommendationCandidate]:
        ranked = sorted(
            candidates,
            key=lambda item: (-item.total_score, item.avid),
        )
        return ranked[: request.limit]
