from nassav.models import Actor, ActorSourceMapping
from nassav.scraper import Javbus
from nassav.source.jable_actor_mapping import (
    persist_actor_source_mapping,
    parse_jable_model_candidates,
    select_best_model_candidate,
)

from .entities import RecommendationCandidate


class RecommendationActorMappingLearner:
    def sync_from_items(self, *, jable, items: list[RecommendationCandidate]) -> dict:
        if jable is None or not items:
            return {
                "javbus_fetched": 0,
                "jable_fetched": 0,
                "saved": 0,
                "unmatched": 0,
                "conflict": 0,
            }

        javbus = Javbus(proxy=getattr(jable, "proxy", None), timeout=jable.timeout)
        javbus_html_cache: dict[str, str | None] = {}
        jable_html_cache: dict[str, str | None] = {}
        stats = {
            "javbus_fetched": 0,
            "jable_fetched": 0,
            "saved": 0,
            "unmatched": 0,
            "conflict": 0,
        }
        base_url = f"https://{jable.domain}/"

        for item in items:
            avid = str(item.avid or "").strip().upper()
            if not avid:
                continue

            javbus_cache_hit = avid in javbus_html_cache
            local_actors = self._resolve_local_actors_from_javbus(
                avid=avid,
                javbus=javbus,
                html_cache=javbus_html_cache,
            )
            if local_actors is None:
                continue
            if not javbus_cache_hit:
                stats["javbus_fetched"] += 1

            actors_needing_mapping = [
                actor
                for actor in local_actors
                if not ActorSourceMapping.objects.filter(
                    actor=actor,
                    source_name="jable",
                    is_active=True,
                ).exists()
            ]
            if not actors_needing_mapping:
                continue

            if avid not in jable_html_cache:
                jable_html_cache[avid] = jable.get_html(avid)
                stats["jable_fetched"] += 1
            jable_html = jable_html_cache.get(avid)
            if not jable_html:
                continue

            candidates = parse_jable_model_candidates(jable_html, base_url=base_url)
            if not candidates:
                continue

            for actor in actors_needing_mapping:
                candidate, confidence, _ = select_best_model_candidate(
                    actor_name=actor.name,
                    candidates=candidates,
                )
                if candidate is None:
                    stats["unmatched"] += 1
                    continue

                ok, _ = persist_actor_source_mapping(
                    actor=actor,
                    candidate=candidate,
                    confidence=confidence,
                    match_method="recommendation_lazy",
                )
                if ok:
                    stats["saved"] += 1
                else:
                    stats["conflict"] += 1

        return stats

    def _resolve_local_actors_from_javbus(
        self,
        *,
        avid: str,
        javbus: Javbus,
        html_cache: dict[str, str | None],
    ) -> list[Actor] | None:
        if avid not in html_cache:
            html_cache[avid] = javbus.get_html(avid)
        html = html_cache.get(avid)
        if not html:
            return None

        metadata = javbus.parse_html(html, avid)
        if not metadata:
            return None

        actor_names = [
            str(name or "").strip()
            for name in metadata.get("actors", []) or []
            if str(name or "").strip()
        ]
        if not actor_names:
            return []

        actors = list(Actor.objects.filter(name__in=actor_names))
        actors_by_name = {actor.name: actor for actor in actors}
        return [actors_by_name[name] for name in actor_names if name in actors_by_name]


recommendation_actor_mapping_learner = RecommendationActorMappingLearner()
