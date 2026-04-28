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
        candidates = self.exclude_seed_blocked_candidates(candidates, request)
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

    def exclude_seed_blocked_candidates(
        self,
        candidates: list[RecommendationCandidate],
        request: RecommendationRequest,
    ) -> list[RecommendationCandidate]:
        if not candidates or not request.seed_blacklist_active:
            return candidates

        from .seed_profiles import recommendation_seed_profile_repository

        blocked_name_keys = request.blocked_seed_name_keys
        blocked_source_keys = request.blocked_seed_source_keys

        output: list[RecommendationCandidate] = []
        for candidate in candidates:
            matched = list(candidate.matched_seeds or [])
            is_blocked = False
            for seed in matched:
                seed_type = str(seed.seed_type or "").strip().lower()
                normalized_value = (
                    recommendation_seed_profile_repository.normalize_value(seed.value)
                )
                if (seed_type, normalized_value) in blocked_name_keys:
                    is_blocked = True
                    break

                lookup_payload = dict(seed.lookup_payload or {})
                source_name = str(lookup_payload.get("source_name", "")).strip().lower()
                source_identifier = self._seed_source_identifier(
                    seed_type, lookup_payload
                )
                if not source_name or not source_identifier:
                    continue
                if (seed_type, source_name, source_identifier) in blocked_source_keys:
                    is_blocked = True
                    break

            # Fallback guard: filter candidates by source slugs extracted during recall,
            # even when blocked tags are not present in matched_seeds.
            if not is_blocked and self._candidate_hits_blocked_source_metrics(
                candidate, blocked_source_keys
            ):
                is_blocked = True

            if not is_blocked:
                output.append(candidate)
        return output

    def _candidate_hits_blocked_source_metrics(
        self,
        candidate: RecommendationCandidate,
        blocked_source_keys: set[tuple[str, str, str]],
    ) -> bool:
        if not blocked_source_keys:
            return False

        source_name = str(candidate.source or "").strip().lower()
        if not source_name:
            return False

        raw_metrics = dict(candidate.raw_metrics or {})
        model_slug = str(raw_metrics.get("model_slug", "")).strip().lower()
        if model_slug and ("actor", source_name, model_slug) in blocked_source_keys:
            return True

        tag_slug = str(raw_metrics.get("tag_slug", "")).strip().lower()
        if tag_slug and ("genre", source_name, tag_slug) in blocked_source_keys:
            return True

        category_slug = str(raw_metrics.get("category_slug", "")).strip().lower()
        if (
            category_slug
            and ("genre", source_name, category_slug) in blocked_source_keys
        ):
            return True

        return False

    def _seed_source_identifier(self, seed_type: str, payload: dict) -> str:
        if seed_type == "actor":
            return str(payload.get("model_slug", "")).strip().lower()
        if seed_type == "genre":
            return str(payload.get("genre_slug", "")).strip().lower()
        return ""

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
