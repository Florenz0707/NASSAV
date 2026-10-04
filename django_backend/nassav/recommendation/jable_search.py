from loguru import logger

from .contracts import RecommendationSource, CandidateInventory

from .base import AbstractRecommender
from .entities import RecommendationCandidate, RecommendationRequest, RecommendationSeed
from .contracts import SeedProvider


class JableSearchRecommender(AbstractRecommender):
    def __init__(
        self,
        jable: RecommendationSource,
        seed_provider: SeedProvider,
        factors=None,
        *,
        candidate_inventory: CandidateInventory,
        diversity_penalty: float = 0.0,
        actor_diversity_weight: float = 1.0,
        genre_diversity_weight: float = 0.5,
        max_pages_per_query: int = 5,
    ):
        super().__init__(factors=factors, candidate_inventory=candidate_inventory)
        self.jable = jable
        self.seed_provider = seed_provider
        self.diversity_penalty = diversity_penalty
        self.actor_diversity_weight = actor_diversity_weight
        self.genre_diversity_weight = genre_diversity_weight
        self.max_pages_per_query = max(max_pages_per_query, 1)

    def _prepare_seed_context(self, request, seeds) -> None:
        self._hydrate_seed_occurrence_tiers(request, seeds)

    def _expand_candidates(self, *, seeds, candidates, request):
        return self._expand_seed_pool_if_needed(
            seeds=seeds, candidates=candidates, request=request
        )

    def _top_up_candidates(self, *, seeds, candidates, request):
        return self._top_up_after_detail_filter_if_needed(
            seeds=seeds, candidates=candidates, request=request
        )

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
                for item in self._recall_keyword_items(keyword, request, seen_avids):
                    raw_results.append(item)
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
        target_limit = self._seed_target_limit(request)
        for page in range(1, self.max_pages_per_query + 1):
            page_results = self._call_get_model_videos(
                model_slug=model_slug,
                page=page,
                sort_by="video_viewed",
                force_refresh=request.force_refresh_external,
            )
            if not page_results:
                break
            added_on_page = 0
            for item in page_results:
                avid = str(item.get("avid", "")).strip().upper()
                if not avid or avid in seen_avids:
                    continue
                seen_avids.add(avid)
                raw_results.append(item)
                added_on_page += 1
                if target_limit > 0 and len(raw_results) >= target_limit:
                    break
            if target_limit > 0 and len(raw_results) >= target_limit:
                break
            if added_on_page == 0:
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
            raw_results.extend(
                self._recall_discovery_pages(
                    request=request,
                    fetch_page=self.jable.discover_hot_items,
                )
            )
        if request.include_latest_updates:
            raw_results.extend(
                self._recall_discovery_pages(
                    request=request,
                    fetch_page=self.jable.discover_latest_updates,
                )
            )

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

    def enrich_candidates(
        self,
        candidates: list[RecommendationCandidate],
        request: RecommendationRequest,
    ) -> list[RecommendationCandidate]:
        if not candidates or request.detail_enrichment_limit <= 0:
            return candidates

        remaining = max(int(request.detail_enrichment_limit), 0)
        for candidate in candidates:
            if remaining <= 0:
                break
            if not self._should_enrich_candidate_detail(candidate, request):
                continue
            detail = self._call_video_detail(candidate, request)
            if not detail:
                continue
            remaining -= 1
            self._apply_video_detail(candidate, detail, request)
        return candidates

    def _recall_keyword_items(
        self,
        keyword: str,
        request: RecommendationRequest,
        seen_avids: set[str],
    ) -> list[dict]:
        raw_results: list[dict] = []
        target_limit = self._seed_target_limit(request)
        for page in range(1, self.max_pages_per_query + 1):
            page_results = self._call_search(
                keyword=keyword,
                page=page,
                force_refresh=request.force_refresh_external,
            )
            if not page_results:
                break
            added_on_page = 0
            for item in page_results:
                avid = str(item.get("avid", "")).strip().upper()
                if not avid or avid in seen_avids:
                    continue
                seen_avids.add(avid)
                raw_results.append(item)
                added_on_page += 1
                if target_limit > 0 and len(raw_results) >= target_limit:
                    break
            if target_limit > 0 and len(raw_results) >= target_limit:
                break
            if added_on_page == 0:
                break
        return raw_results

    def _recall_discovery_pages(
        self,
        *,
        request: RecommendationRequest,
        fetch_page,
    ) -> list[dict]:
        raw_results: list[dict] = []
        seen_avids: set[str] = set()
        target_limit = self._discovery_target_limit(request)
        for page in range(1, self.max_pages_per_query + 1):
            page_results = self._call_discovery_fetch(
                fetch_page=fetch_page,
                page=page,
                force_refresh=request.force_refresh_external,
            )
            if not page_results:
                break
            added_on_page = 0
            for item in page_results:
                avid = str(item.get("avid", "")).strip().upper()
                if not avid or avid in seen_avids:
                    continue
                seen_avids.add(avid)
                raw_results.append(item)
                added_on_page += 1
                if target_limit > 0 and len(raw_results) >= target_limit:
                    break
            if target_limit > 0 and len(raw_results) >= target_limit:
                break
            if added_on_page == 0:
                break
        return raw_results

    def _seed_target_limit(self, request: RecommendationRequest) -> int:
        if request.per_seed_limit <= 0:
            return max(request.limit, 0)
        if request.recently_recommended_avids or request.recent_recommendation_counts:
            return request.per_seed_limit
        if request.limit <= 0:
            return request.per_seed_limit
        return min(request.per_seed_limit, request.limit)

    def _discovery_target_limit(self, request: RecommendationRequest) -> int:
        if request.discovery_limit <= 0:
            return max(request.limit, 0)
        if request.recently_recommended_avids or request.recent_recommendation_counts:
            return request.discovery_limit
        if request.limit <= 0:
            return request.discovery_limit
        return min(request.discovery_limit, request.limit)

    def _call_get_model_videos(
        self,
        *,
        model_slug: str,
        page: int,
        sort_by: str,
        force_refresh: bool,
    ) -> list[dict]:
        try:
            return self.jable.get_model_videos(
                model_slug=model_slug,
                page=page,
                sort_by=sort_by,
                force_refresh=force_refresh,
            )
        except TypeError:
            return self.jable.get_model_videos(
                model_slug=model_slug,
                page=page,
                sort_by=sort_by,
            )

    def _call_search(
        self,
        *,
        keyword: str,
        page: int,
        force_refresh: bool,
    ) -> list[dict]:
        try:
            return self.jable.search(
                keyword,
                page=page,
                force_refresh=force_refresh,
            )
        except TypeError:
            return self.jable.search(keyword, page=page)

    def _call_discovery_fetch(
        self,
        *,
        fetch_page,
        page: int,
        force_refresh: bool,
    ) -> list[dict]:
        try:
            return fetch_page(page=page, force_refresh=force_refresh)
        except TypeError:
            return fetch_page(page=page)

    def _call_video_detail(
        self,
        candidate: RecommendationCandidate,
        request: RecommendationRequest,
    ) -> dict:
        fetch_detail = getattr(self.jable, "get_video_detail", None)
        if fetch_detail is None:
            return {}
        try:
            return fetch_detail(
                candidate.avid,
                candidate.detail_url,
                force_refresh=request.force_refresh_external,
            )
        except TypeError:
            try:
                return fetch_detail(candidate.avid, candidate.detail_url)
            except TypeError:
                return fetch_detail(candidate.avid)

    def _apply_video_detail(
        self,
        candidate: RecommendationCandidate,
        detail: dict,
        request: RecommendationRequest,
    ) -> None:
        raw_metrics = dict(candidate.raw_metrics or {})
        raw_metrics["detail_enriched"] = True
        raw_metrics["detail"] = dict(detail)
        for source_key, target_key in (
            ("actors", "detail_actors"),
            ("actor_slugs", "detail_actor_slugs"),
            ("genres", "detail_genres"),
            ("genre_slugs", "detail_genre_slugs"),
            ("tag_slugs", "detail_tag_slugs"),
            ("category_slugs", "detail_category_slugs"),
        ):
            values = [
                str(value).strip()
                for value in list(detail.get(source_key) or [])
                if str(value).strip()
            ]
            if values:
                raw_metrics[target_key] = values
        candidate.raw_metrics = raw_metrics

        if detail.get("title") and not candidate.title:
            candidate.title = str(detail["title"]).strip()
        if detail.get("cover_url") and not candidate.cover_url:
            candidate.cover_url = str(detail["cover_url"]).strip()

        self._attach_detail_matched_seeds(candidate, request)

    def _should_enrich_candidate_detail(
        self,
        candidate: RecommendationCandidate,
        request: RecommendationRequest,
    ) -> bool:
        raw_metrics = dict(candidate.raw_metrics or {})
        if raw_metrics.get("detail_enriched"):
            return False
        if raw_metrics.get("discovery_sources"):
            return True
        if not request.seed_blacklist_active:
            return False
        if not candidate.matched_seeds:
            return True
        return bool(request.blocked_seed_name_keys or request.blocked_seed_source_keys)

    def _attach_detail_matched_seeds(
        self,
        candidate: RecommendationCandidate,
        request: RecommendationRequest,
    ) -> None:
        if not request.active_seeds:
            return

        raw_metrics = dict(candidate.raw_metrics or {})
        detail_actors = self._normalized_value_set(raw_metrics.get("detail_actors"))
        detail_genres = self._normalized_value_set(raw_metrics.get("detail_genres"))
        detail_actor_slugs = self._normalized_slug_set(
            raw_metrics.get("detail_actor_slugs")
        )
        detail_genre_slugs = self._normalized_slug_set(
            raw_metrics.get("detail_genre_slugs")
        )

        for seed in request.active_seeds:
            lookup_payload = dict(seed.lookup_payload or {})
            if seed.seed_type == "actor":
                model_slug = str(lookup_payload.get("model_slug", "")).strip().lower()
                if (
                    self._normalize_text(seed.value) in detail_actors
                    or model_slug
                    and model_slug in detail_actor_slugs
                ):
                    candidate.add_seed(seed)
            elif seed.seed_type == "genre":
                genre_slug = str(lookup_payload.get("genre_slug", "")).strip().lower()
                if (
                    self._normalize_text(seed.value) in detail_genres
                    or genre_slug
                    and genre_slug in detail_genre_slugs
                ):
                    candidate.add_seed(seed)

    def _normalized_value_set(self, values) -> set[str]:
        return {
            self._normalize_text(value)
            for value in list(values or [])
            if self._normalize_text(value)
        }

    def _normalized_slug_set(self, values) -> set[str]:
        return {
            str(value or "").strip().lower()
            for value in list(values or [])
            if str(value or "").strip()
        }

    def _normalize_text(self, value: str) -> str:
        return " ".join(str(value or "").strip().casefold().split())

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

    def _hydrate_seed_occurrence_tiers(
        self,
        request: RecommendationRequest,
        seeds: list[RecommendationSeed],
    ) -> None:
        request.seed_occurrence_tiers = self._build_seed_occurrence_tiers(seeds)

    def _build_seed_occurrence_tiers(
        self,
        seeds: list[RecommendationSeed],
    ) -> dict[str, str]:
        grouped: dict[str, list[RecommendationSeed]] = {}
        for seed in seeds:
            grouped.setdefault(seed.seed_type, []).append(seed)

        tiers: dict[str, str] = {}
        for seed_group in grouped.values():
            ordered = sorted(
                seed_group,
                key=lambda item: (
                    -(item.resource_count or 0),
                    -item.preference_score,
                    item.value,
                ),
            )
            total = len(ordered)
            if total <= 0:
                continue
            high_size = max(total // 3, 1)
            low_size = max(total // 3, 1)
            low_start = max(total - low_size, high_size)

            for index, seed in enumerate(ordered):
                if index < high_size:
                    tier = "high"
                elif index >= low_start:
                    tier = "low"
                else:
                    tier = "mid"
                tiers[f"{seed.seed_type}:{seed.value}"] = tier

        return tiers

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
        max_rounds: int = 3,
    ) -> tuple[list[RecommendationSeed], list[RecommendationCandidate]]:
        if self.count_preferred_candidates(candidates, request) >= request.limit:
            return seeds, candidates

        expanded_seeds = list(seeds)
        merged_candidates: dict[str, RecommendationCandidate] = {
            candidate.avid: candidate for candidate in candidates
        }
        batch_size = max(request.actor_seed_limit + request.genre_seed_limit, 4)
        expansion_rounds = 0

        while self.count_preferred_candidates(
            list(merged_candidates.values()), request
        ) < request.limit and expansion_rounds < max(int(max_rounds), 1):
            extra_seeds = self.seed_provider.get_additional_seeds(
                request,
                used_seeds=expanded_seeds,
                batch_size=batch_size,
            )
            if not extra_seeds:
                break

            extra_seeds = self.exclude_seed_blocked_seeds(extra_seeds, request)
            if not extra_seeds:
                break

            expanded_seeds.extend(extra_seeds)
            extra_candidates = self.recall_candidates(extra_seeds, request)
            extra_candidates = self.exclude_existing_resources(
                extra_candidates, request
            )
            extra_candidates = self.filter_blocklisted_candidates(
                extra_candidates, request
            )
            for candidate in extra_candidates:
                self._merge_candidate(merged_candidates, candidate)
            expansion_rounds += 1

        return expanded_seeds, list(merged_candidates.values())

    def _top_up_after_detail_filter_if_needed(
        self,
        *,
        seeds: list[RecommendationSeed],
        candidates: list[RecommendationCandidate],
        request: RecommendationRequest,
    ) -> tuple[list[RecommendationSeed], list[RecommendationCandidate]]:
        expanded_seeds = list(seeds)
        output_candidates = list(candidates)
        top_up_rounds = 0

        while (
            self.count_preferred_candidates(output_candidates, request) < request.limit
            and top_up_rounds < 3
        ):
            previous_seed_count = len(expanded_seeds)
            previous_avids = {candidate.avid for candidate in output_candidates}

            expanded_seeds, output_candidates = self._expand_seed_pool_if_needed(
                seeds=expanded_seeds,
                candidates=output_candidates,
                request=request,
                max_rounds=1,
            )
            current_avids = {candidate.avid for candidate in output_candidates}
            if (
                len(expanded_seeds) == previous_seed_count
                and current_avids == previous_avids
            ):
                break

            request.active_seeds = list(expanded_seeds)
            self._hydrate_seed_occurrence_tiers(request, expanded_seeds)
            output_candidates = self.filter_recent_recommendations(
                output_candidates,
                request,
            )
            output_candidates = self.enrich_candidates(output_candidates, request)
            output_candidates = self.filter_blocklisted_candidates(
                output_candidates,
                request,
            )
            top_up_rounds += 1

        return expanded_seeds, output_candidates
