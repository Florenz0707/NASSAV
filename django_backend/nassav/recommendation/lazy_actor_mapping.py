from loguru import logger

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
        return self.sync_from_avids(
            jable=jable,
            avids=[
                str(item.avid or "").strip().upper()
                for item in items
                if str(item.avid or "").strip()
            ],
        )

    def sync_from_avids(self, *, jable, avids: list[str]) -> dict:
        if jable is None or not avids:
            return {
                "javbus_fetched": 0,
                "jable_fetched": 0,
                "saved": 0,
                "unmatched": 0,
                "conflict": 0,
                "skipped_errors": 0,
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
            "skipped_errors": 0,
        }
        base_url = f"https://{jable.domain}/"

        for raw_avid in avids:
            avid = str(raw_avid or "").strip().upper()
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
                try:
                    jable_html_cache[avid] = jable.get_html(avid)
                except Exception as exc:
                    logger.warning(
                        f"[RecommendationActorMappingLearner] 跳过 {avid}: "
                        f"Jable 抓取失败: {exc}"
                    )
                    jable_html_cache[avid] = None
                    stats["skipped_errors"] += 1
                else:
                    stats["jable_fetched"] += 1
            jable_html = jable_html_cache.get(avid)
            if not jable_html:
                continue

            try:
                candidates = parse_jable_model_candidates(jable_html, base_url=base_url)
            except Exception as exc:
                logger.warning(
                    f"[RecommendationActorMappingLearner] 跳过 {avid}: "
                    f"Jable models 解析失败: {exc}"
                )
                stats["skipped_errors"] += 1
                continue
            if not candidates:
                continue

            for actor in actors_needing_mapping:
                try:
                    candidate, confidence, _ = select_best_model_candidate(
                        actor_name=actor.name,
                        candidates=candidates,
                    )
                except Exception as exc:
                    logger.warning(
                        "[RecommendationActorMappingLearner] 跳过 "
                        f"{avid}/{actor.name}: model 匹配失败: {exc}"
                    )
                    stats["skipped_errors"] += 1
                    continue
                if candidate is None:
                    stats["unmatched"] += 1
                    continue

                try:
                    ok, _ = persist_actor_source_mapping(
                        actor=actor,
                        candidate=candidate,
                        confidence=confidence,
                        match_method="recommendation_lazy",
                    )
                except Exception as exc:
                    logger.warning(
                        "[RecommendationActorMappingLearner] 跳过 "
                        f"{avid}/{actor.name}: mapping 持久化失败: {exc}"
                    )
                    stats["skipped_errors"] += 1
                    continue
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
            try:
                html_cache[avid] = javbus.get_html(avid)
            except Exception as exc:
                logger.warning(
                    f"[RecommendationActorMappingLearner] 跳过 {avid}: "
                    f"JavBus 抓取失败: {exc}"
                )
                html_cache[avid] = None
        html = html_cache.get(avid)
        if not html:
            return None

        try:
            metadata = javbus.parse_html(html, avid)
        except Exception as exc:
            logger.warning(
                f"[RecommendationActorMappingLearner] 跳过 {avid}: "
                f"JavBus 解析失败: {exc}"
            )
            return None
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
