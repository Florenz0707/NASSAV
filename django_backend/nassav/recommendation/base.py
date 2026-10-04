from abc import ABC, abstractmethod
from hashlib import blake2b

from copy import deepcopy
from .contracts import CandidateInventory
from .seed_policy import normalize_seed_value

from .entities import RecommendationCandidate, RecommendationRequest, RecommendationRun
from .factors import RecommendationFactor


class AbstractRecommender(ABC):
    def __init__(
        self,
        factors: list[RecommendationFactor] | None = None,
        *,
        candidate_inventory: CandidateInventory,
    ):
        self.factors = factors or []
        self.candidate_inventory = candidate_inventory

    def recommend(self, request: RecommendationRequest):
        request = deepcopy(request)
        seeds = self.build_seeds(request)
        seeds = self.exclude_seed_blocked_seeds(seeds, request)
        request.active_seeds = list(seeds)
        self._prepare_seed_context(request, seeds)
        candidates = self.recall_candidates(seeds, request)
        candidates = self.exclude_existing_resources(candidates, request)
        candidates = self.filter_blocklisted_candidates(candidates, request)
        seeds, candidates = self._expand_candidates(
            seeds=seeds,
            candidates=candidates,
            request=request,
        )
        request.active_seeds = list(seeds)
        candidates = self.exclude_existing_resources(candidates, request)
        candidates = self.filter_blocklisted_candidates(candidates, request)
        self._prepare_seed_context(request, seeds)
        candidates = self.filter_recent_recommendations(candidates, request)
        candidates = self.enrich_candidates(candidates, request)
        candidates = self.filter_blocklisted_candidates(candidates, request)
        seeds, candidates = self._top_up_candidates(
            seeds=seeds,
            candidates=candidates,
            request=request,
        )
        candidates = self.score_candidates(candidates, request)
        items = self.rank_and_trim(candidates, request)
        items = self.filter_blocklisted_candidates(items, request)

        return RecommendationRun(seeds=seeds, items=items, execution_request=request)

    def _prepare_seed_context(self, request, seeds) -> None:
        pass

    def _expand_candidates(self, *, seeds, candidates, request):
        return seeds, candidates

    def _top_up_candidates(self, *, seeds, candidates, request):
        return seeds, candidates

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
        candidates = self.exclude_avid_blocklisted_resources(candidates, request)
        candidates = self.exclude_seed_blocked_candidates(candidates, request)
        return self.filter_recent_recommendations(candidates, request)

    def filter_blocklisted_candidates(
        self,
        candidates: list[RecommendationCandidate],
        request: RecommendationRequest,
    ) -> list[RecommendationCandidate]:
        candidates = self.exclude_avid_blocklisted_resources(candidates, request)
        return self.exclude_seed_blocked_candidates(candidates, request)

    def exclude_seed_blocked_seeds(
        self,
        seeds,
        request: RecommendationRequest,
    ):
        if not seeds or not request.seed_blacklist_active:
            return seeds

        output = []
        for seed in seeds:
            if self._seed_hits_blocklist(seed, request):
                continue
            output.append(seed)
        return output

    def _seed_hits_blocklist(
        self,
        seed,
        request: RecommendationRequest,
    ) -> bool:

        seed_type = str(seed.seed_type or "").strip().lower()
        normalized_value = normalize_seed_value(seed.value)
        if (seed_type, normalized_value) in request.blocked_seed_name_keys:
            return True

        lookup_payload = dict(seed.lookup_payload or {})
        source_name = str(lookup_payload.get("source_name", "")).strip().lower()
        source_identifier = self._seed_source_identifier(seed_type, lookup_payload)
        return bool(
            source_name
            and source_identifier
            and (seed_type, source_name, source_identifier)
            in request.blocked_seed_source_keys
        )

    def exclude_existing_resources(
        self,
        candidates: list[RecommendationCandidate],
        request: RecommendationRequest,
    ) -> list[RecommendationCandidate]:
        if not candidates:
            return candidates

        if request.exclude_existing:
            existing_avids = self.candidate_inventory.existing(
                {candidate.avid for candidate in candidates}
            )
            candidates = [
                candidate
                for candidate in candidates
                if candidate.avid not in existing_avids
            ]

        return candidates

    def exclude_avid_blocklisted_resources(
        self,
        candidates: list[RecommendationCandidate],
        request: RecommendationRequest,
    ) -> list[RecommendationCandidate]:
        if not candidates or not request.blocked_avid_blocklist:
            return candidates

        return [
            candidate
            for candidate in candidates
            if candidate.avid not in request.blocked_avid_blocklist
        ]

    def exclude_seed_blocked_candidates(
        self,
        candidates: list[RecommendationCandidate],
        request: RecommendationRequest,
    ) -> list[RecommendationCandidate]:
        if not candidates or not request.seed_blacklist_active:
            return candidates

        blocked_name_keys = request.blocked_seed_name_keys
        blocked_source_keys = request.blocked_seed_source_keys

        output: list[RecommendationCandidate] = []
        for candidate in candidates:
            matched = list(candidate.matched_seeds or [])
            is_blocked = False
            for seed in matched:
                seed_type = str(seed.seed_type or "").strip().lower()
                normalized_value = normalize_seed_value(seed.value)
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

            if not is_blocked and self._candidate_hits_blocked_detail_values(
                candidate,
                blocked_name_keys,
                blocked_source_keys,
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

    def _candidate_hits_blocked_detail_values(
        self,
        candidate: RecommendationCandidate,
        blocked_name_keys: set[tuple[str, str]],
        blocked_source_keys: set[tuple[str, str, str]],
    ) -> bool:
        raw_metrics = dict(candidate.raw_metrics or {})

        for value in self._normalized_metric_values(raw_metrics.get("detail_actors")):
            if ("actor", value) in blocked_name_keys:
                return True
        for value in self._normalized_metric_values(raw_metrics.get("detail_genres")):
            if ("genre", value) in blocked_name_keys:
                return True

        source_name = str(candidate.source or "").strip().lower()
        if source_name:
            detail_actor_slugs = self._normalized_metric_slugs(
                raw_metrics.get("detail_actor_slugs")
            )
            for slug in detail_actor_slugs:
                if ("actor", source_name, slug) in blocked_source_keys:
                    return True

            detail_genre_slugs = set()
            for metric_key in (
                "detail_genre_slugs",
                "detail_tag_slugs",
                "detail_category_slugs",
            ):
                detail_genre_slugs.update(
                    self._normalized_metric_slugs(raw_metrics.get(metric_key))
                )
            for slug in detail_genre_slugs:
                if ("genre", source_name, slug) in blocked_source_keys:
                    return True

        return False

    def _normalized_metric_values(self, values) -> set[str]:
        return {
            " ".join(str(value or "").strip().casefold().split())
            for value in list(values or [])
            if str(value or "").strip()
        }

    def _normalized_metric_slugs(self, values) -> set[str]:
        return {
            str(value or "").strip().lower()
            for value in list(values or [])
            if str(value or "").strip()
        }

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
