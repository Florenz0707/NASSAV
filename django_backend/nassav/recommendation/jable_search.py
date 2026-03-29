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

    def recommend(self, request: RecommendationRequest):
        seeds = self.build_seeds(request)
        candidates = self.recall_candidates(seeds, request)
        candidates = self.exclude_existing_resources(candidates, request)
        candidates = self.exclude_feedback_blocked_resources(candidates, request)
        seeds, candidates = self._expand_seed_pool_if_needed(
            seeds=seeds,
            candidates=candidates,
            request=request,
        )
        candidates = self.filter_recent_recommendations(candidates, request)
        candidates = self.enrich_candidates(candidates, request)
        candidates = self.score_candidates(candidates, request)
        items = self.rank_and_trim(candidates, request)
        from .entities import RecommendationRun

        return RecommendationRun(seeds=seeds, items=items)

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
                self._merge_candidate(merged, candidate)

        for candidate in self.recall_discovery_candidates(request):
            self._merge_candidate(merged, candidate)

        return list(merged.values())

    def recall_by_seed(
        self,
        seed: RecommendationSeed,
        request: RecommendationRequest,
    ) -> list[RecommendationCandidate]:
        raw_results: list[dict] = []
        seen_avids: set[str] = set()
        raw_results.extend(self._recall_actor_model_items(seed, request, seen_avids))
        if not raw_results:
            search_terms = self._search_terms_for_seed(seed)
            for keyword in search_terms:
                for item in self.jable.search(keyword, page=1):
                    avid = str(item.get("avid", "")).strip().upper()
                    if not avid or avid in seen_avids:
                        continue
                    seen_avids.add(avid)
                    raw_results.append(item)
                    if (
                        request.per_seed_limit > 0
                        and len(raw_results) >= request.per_seed_limit
                    ):
                        break
                if (
                    request.per_seed_limit > 0
                    and len(raw_results) >= request.per_seed_limit
                ):
                    break

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

    def _recall_actor_model_items(
        self,
        seed: RecommendationSeed,
        request: RecommendationRequest,
        seen_avids: set[str],
    ) -> list[dict]:
        if seed.seed_type != "actor":
            return []

        lookup_payload = dict(seed.lookup_payload or {})
        if lookup_payload.get("source_name") != "jable":
            return []

        model_slug = str(lookup_payload.get("model_slug", "")).strip()
        if not model_slug:
            return []

        raw_results: list[dict] = []
        for item in self.jable.get_model_videos(
            model_slug=model_slug,
            page=1,
            sort_by="video_viewed",
        ):
            avid = str(item.get("avid", "")).strip().upper()
            if not avid or avid in seen_avids:
                continue
            seen_avids.add(avid)
            raw_results.append(item)
            if (
                request.per_seed_limit > 0
                and len(raw_results) >= request.per_seed_limit
            ):
                break
        return raw_results

    def recall_discovery_candidates(
        self,
        request: RecommendationRequest,
    ) -> list[RecommendationCandidate]:
        if request.discovery_limit <= 0:
            return []

        raw_results: list[dict] = []
        if request.include_hot_board:
            raw_results.extend(self.jable.discover_hot_items(page=1))
        if request.include_latest_updates:
            raw_results.extend(self.jable.discover_latest_updates(page=1))

        candidates: list[RecommendationCandidate] = []
        seen_avids: set[str] = set()
        for index, item in enumerate(raw_results, start=1):
            avid = str(item.get("avid", "")).strip().upper()
            if not avid or avid in seen_avids:
                continue
            seen_avids.add(avid)
            candidates.append(
                RecommendationCandidate(
                    avid=avid,
                    title=str(item.get("title", "")).strip(),
                    detail_url=str(item.get("detail_url", "")).strip(),
                    cover_url=str(item.get("cover_url", "")).strip(),
                    source=str(item.get("source", "Jable")).strip() or "Jable",
                    search_rank=index,
                    raw_metrics=dict(item.get("metrics") or {}),
                )
            )
            if len(candidates) >= request.discovery_limit:
                break
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
            if key == "discovery_sources":
                existing_values = list(merged.get(key) or [])
                for source in value or []:
                    if source not in existing_values:
                        existing_values.append(source)
                merged[key] = existing_values
                continue
            if key not in merged or not merged[key]:
                merged[key] = value
        return merged

    def _merge_candidate(
        self,
        merged: dict[str, RecommendationCandidate],
        candidate: RecommendationCandidate,
    ) -> None:
        existing = merged.get(candidate.avid)
        if existing is None:
            merged[candidate.avid] = candidate
            return

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

    def _search_terms_for_seed(self, seed: RecommendationSeed) -> list[str]:
        search_terms: list[str] = []
        seen: set[str] = set()
        for term in [seed.value, *seed.aliases]:
            normalized = str(term or "").strip()
            if not normalized:
                continue
            token = normalized.casefold()
            if token in seen:
                continue
            seen.add(token)
            search_terms.append(normalized)
        return search_terms

    def _expand_seed_pool_if_needed(
        self,
        *,
        seeds: list[RecommendationSeed],
        candidates: list[RecommendationCandidate],
        request: RecommendationRequest,
    ) -> tuple[list[RecommendationSeed], list[RecommendationCandidate]]:
        if self.count_preferred_candidates(candidates, request) >= request.limit:
            return seeds, candidates

        expanded_seeds = list(seeds)
        merged_candidates: dict[str, RecommendationCandidate] = {
            candidate.avid: candidate for candidate in candidates
        }
        batch_size = max(request.actor_seed_limit + request.genre_seed_limit, 4)
        expansion_rounds = 0

        while (
            self.count_preferred_candidates(list(merged_candidates.values()), request)
            < request.limit
            and expansion_rounds < 3
        ):
            extra_seeds = self.seed_provider.get_additional_seeds(
                request,
                used_seeds=expanded_seeds,
                batch_size=batch_size,
            )
            if not extra_seeds:
                break

            expanded_seeds.extend(extra_seeds)
            extra_candidates = self.recall_candidates(extra_seeds, request)
            extra_candidates = self.exclude_existing_resources(
                extra_candidates, request
            )
            extra_candidates = self.exclude_feedback_blocked_resources(
                extra_candidates, request
            )
            for candidate in extra_candidates:
                self._merge_candidate(merged_candidates, candidate)
            expansion_rounds += 1

        return expanded_seeds, list(merged_candidates.values())
