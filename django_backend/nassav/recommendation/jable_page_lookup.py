from .entities import RecommendationCandidate, RecommendationRequest, RecommendationSeed
from .jable_search import JableSearchRecommender


class JablePageLookupRecommender(JableSearchRecommender):
    def recall_by_seed(
        self,
        seed: RecommendationSeed,
        request: RecommendationRequest,
    ) -> list[RecommendationCandidate]:
        raw_results: list[dict] = []
        seen_avids: set[str] = set()

        raw_results.extend(self._recall_actor_model_items(seed, request, seen_avids))
        raw_results.extend(self._recall_genre_page_items(seed, request, seen_avids))

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

    def _recall_genre_page_items(
        self,
        seed: RecommendationSeed,
        request: RecommendationRequest,
        seen_avids: set[str],
    ) -> list[dict]:
        if seed.seed_type != "genre":
            return []

        lookup_payload = dict(seed.lookup_payload or {})
        if lookup_payload.get("source_name") != "jable":
            return []

        genre_slug = str(lookup_payload.get("genre_slug", "")).strip()
        if not genre_slug:
            return []

        taxonomy = self._resolve_genre_taxonomy(lookup_payload)
        fetch_page = self.jable.get_category_videos
        if taxonomy == "tag":
            fetch_page = self.jable.get_tag_videos

        raw_results: list[dict] = []
        target_limit = self._seed_target_limit(request)
        for page in range(1, self.max_pages_per_query + 1):
            page_results = self._call_genre_page_fetch(
                fetch_page=fetch_page,
                genre_slug=genre_slug,
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

    def _resolve_genre_taxonomy(self, payload: dict) -> str:
        taxonomy = str(payload.get("genre_taxonomy", "")).strip().lower()
        if taxonomy in {"tag", "category"}:
            return taxonomy

        source_genre_url = str(payload.get("source_genre_url", "")).strip().lower()
        if "/categories/" in source_genre_url:
            return "category"
        if "/tags/" in source_genre_url:
            return "tag"
        return "tag"

    def _call_genre_page_fetch(
        self,
        *,
        fetch_page,
        genre_slug: str,
        page: int,
        force_refresh: bool,
    ) -> list[dict]:
        try:
            return fetch_page(
                genre_slug,
                page=page,
                force_refresh=force_refresh,
            )
        except TypeError:
            return fetch_page(genre_slug, page=page)
