from abc import ABC, abstractmethod
from hashlib import blake2b

from nassav.models import AVResource

from .entities import RecommendationCandidate, RecommendationRequest, RecommendationRun
from .factors import RecommendationFactor


class AbstractRecommender(ABC):
    def __init__(self, factors: list[RecommendationFactor] | None = None):
        self.factors = factors or []

    def recommend(self, request: RecommendationRequest) -> RecommendationRun:
        seeds = self.build_seeds(request)
        candidates = self.recall_candidates(seeds, request)
        candidates = self.filter_existing_resources(candidates, request)
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
        request: RecommendationRequest,
    ) -> list[RecommendationCandidate]:
        candidates = self.exclude_existing_resources(candidates, request)
        candidates = self.exclude_feedback_blocked_resources(candidates, request)
        return self.filter_recent_recommendations(candidates, request)

    def exclude_existing_resources(
        self,
        candidates: list[RecommendationCandidate],
        request: RecommendationRequest,
    ) -> list[RecommendationCandidate]:
        if not candidates:
            return candidates

        if request.exclude_existing:
            existing_avids = set(
                AVResource.objects.filter(
                    avid__in=[candidate.avid for candidate in candidates]
                ).values_list("avid", flat=True)
            )
            candidates = [
                candidate
                for candidate in candidates
                if candidate.avid not in existing_avids
            ]

        return candidates

    def exclude_feedback_blocked_resources(
        self,
        candidates: list[RecommendationCandidate],
        request: RecommendationRequest,
    ) -> list[RecommendationCandidate]:
        if not candidates or not request.blocked_feedback_avids:
            return candidates

        return [
            candidate
            for candidate in candidates
            if candidate.avid not in request.blocked_feedback_avids
        ]

    def filter_recent_recommendations(
        self,
        candidates: list[RecommendationCandidate],
        request: RecommendationRequest,
    ) -> list[RecommendationCandidate]:
        if not candidates:
            return candidates

        if not request.recently_recommended_avids:
            return candidates

        recent_avids = set(request.recently_recommended_avids)
        fresh_candidates = [
            candidate for candidate in candidates if candidate.avid not in recent_avids
        ]
        if not fresh_candidates:
            return candidates

        if len(fresh_candidates) >= request.limit:
            return fresh_candidates

        supplemental_candidates = [
            candidate for candidate in candidates if candidate.avid in recent_avids
        ]
        if supplemental_candidates:
            return fresh_candidates + supplemental_candidates
        return candidates

    def count_preferred_candidates(
        self,
        candidates: list[RecommendationCandidate],
        request: RecommendationRequest,
    ) -> int:
        if not candidates:
            return 0

        if not request.recently_recommended_avids:
            return len(candidates)

        recent_avids = set(request.recently_recommended_avids)
        return sum(1 for candidate in candidates if candidate.avid not in recent_avids)

    def prioritize_fresh_candidates(
        self,
        candidates: list[RecommendationCandidate],
        request: RecommendationRequest,
    ) -> list[RecommendationCandidate]:
        if not candidates or not request.recently_recommended_avids:
            return candidates

        recent_avids = set(request.recently_recommended_avids)
        fresh_candidates = [
            candidate for candidate in candidates if candidate.avid not in recent_avids
        ]
        if not fresh_candidates:
            return candidates

        recent_candidates = [
            candidate for candidate in candidates if candidate.avid in recent_avids
        ]
        return fresh_candidates + recent_candidates

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
        ranked = self.rank_candidates(candidates, request)
        reranked = self.rerank_candidates(ranked, request)
        reranked = self.prioritize_fresh_candidates(reranked, request)
        return reranked[: request.limit]

    def rank_candidates(
        self,
        candidates: list[RecommendationCandidate],
        request: RecommendationRequest,
    ) -> list[RecommendationCandidate]:
        _ = request
        return sorted(
            candidates,
            key=lambda item: (
                -item.total_score,
                item.search_rank if item.search_rank is not None else 10**9,
                self._seeded_rank_token(item, request),
            ),
        )

    def rerank_candidates(
        self,
        ranked_candidates: list[RecommendationCandidate],
        request: RecommendationRequest,
    ) -> list[RecommendationCandidate]:
        _ = request
        return ranked_candidates

    def _seeded_rank_token(
        self,
        candidate: RecommendationCandidate,
        request: RecommendationRequest,
    ) -> str:
        digest = blake2b(
            f"{request.random_seed}:{candidate.avid}".encode("utf-8"),
            digest_size=8,
        ).hexdigest()
        return digest
