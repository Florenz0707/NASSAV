import json
import re
import secrets
from hashlib import sha256

from django.db import transaction
from django.db.models import Count, Q, F
from django.utils import timezone

from nassav.models import (
    RecommendationAvidBlocklist,
    RecommendationFeedback,
    RecommendationItem,
    RecommendationItemSeed,
    RecommendationSeedProfile,
    RecommendationSnapshot,
)

from .entities import RecommendationExecution, RecommendationRequest
from .seed_profiles import recommendation_seed_profile_repository


class RecommendationSnapshotRepository:
    def next_random_seed(self) -> int:
        return secrets.randbelow(2**31 - 1) + 1

    def build_request_fingerprint(
        self,
        *,
        recommender_id: str,
        strategy_id: str,
        request: RecommendationRequest,
    ) -> str:
        payload = {
            "recommender": recommender_id,
            "strategy": strategy_id,
            "limit": request.limit,
            "per_seed_limit": request.per_seed_limit,
            "actor_seed_limit": request.actor_seed_limit,
            "genre_seed_limit": request.genre_seed_limit,
            "seed_types": list(request.seed_types),
            "exclude_existing": request.exclude_existing,
            "avoid_recent_recommendations": request.avoid_recent_recommendations,
            "recent_snapshot_limit": request.recent_snapshot_limit,
            "recent_item_limit": request.recent_item_limit,
            "include_hot_board": request.include_hot_board,
            "include_latest_updates": request.include_latest_updates,
            "discovery_limit": request.discovery_limit,
            "detail_enrichment_limit": request.detail_enrichment_limit,
            "type_preference": request.type_preference,
            "actor_preference": request.actor_preference,
            "genre_preference": request.genre_preference,
            "force_refresh_external": request.force_refresh_external,
        }
        return sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()

    def get_recent_recommended_avids(
        self,
        *,
        recommender_id: str,
        strategy_id: str,
        request_fingerprint: str,
        snapshot_limit: int,
        item_limit: int,
    ) -> list[str]:
        if snapshot_limit <= 0 or item_limit <= 0:
            return []

        snapshot_ids = list(
            RecommendationSnapshot.objects.filter(
                recommender_id=recommender_id,
                strategy_id=strategy_id,
                request_fingerprint=request_fingerprint,
            )
            .order_by("-generated_at", "-id")
            .values_list("id", flat=True)[:snapshot_limit]
        )
        if not snapshot_ids:
            return []

        items = RecommendationItem.objects.filter(
            snapshot_id__in=snapshot_ids
        ).order_by(
            "-snapshot__generated_at",
            "rank",
            "id",
        )

        output: list[str] = []
        seen: set[str] = set()
        for avid in items.values_list("avid", flat=True):
            if avid in seen:
                continue
            seen.add(avid)
            output.append(avid)
            if len(output) >= item_limit:
                break
        return output

    def get_recent_recommendation_counts(
        self,
        *,
        recommender_id: str,
        snapshot_limit: int,
        item_limit: int,
    ) -> dict[str, int]:
        if snapshot_limit <= 0 or item_limit <= 0:
            return {}

        snapshot_ids = list(
            RecommendationSnapshot.objects.filter(
                recommender_id=recommender_id,
            )
            .order_by("-generated_at", "-pk")
            .values_list("pk", flat=True)[:snapshot_limit]
        )
        if not snapshot_ids:
            return {}

        items = RecommendationItem.objects.filter(
            snapshot_id__in=snapshot_ids
        ).order_by(
            "-snapshot__generated_at",
            "rank",
            "pk",
        )

        counts: dict[str, int] = {}
        seen_pairs: set[tuple[int, str]] = set()
        seen_rows = 0
        for snapshot_id, avid in items.values_list("snapshot_id", "avid"):
            pair = (snapshot_id, avid)
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            counts[avid] = counts.get(avid, 0) + 1
            seen_rows += 1
            if seen_rows >= item_limit:
                break
        return counts

    def get_recent_seed_counts(
        self,
        *,
        recommender_id: str,
        snapshot_limit: int,
        item_limit: int,
    ) -> dict[str, int]:
        if snapshot_limit <= 0 or item_limit <= 0:
            return {}

        snapshot_ids = list(
            RecommendationSnapshot.objects.filter(
                recommender_id=recommender_id,
            )
            .order_by("-generated_at", "-pk")
            .values_list("pk", flat=True)[:snapshot_limit]
        )
        if not snapshot_ids:
            return {}

        counts: dict[str, int] = {}
        item_ids = list(
            RecommendationItem.objects.filter(snapshot_id__in=snapshot_ids)
            .order_by("-snapshot__generated_at", "rank", "pk")
            .values_list("pk", flat=True)[:item_limit]
        )
        if not item_ids:
            return counts

        for seed_type, seed_value in RecommendationItemSeed.objects.filter(
            item_id__in=item_ids
        ).values_list("seed_type", "seed_value"):
            normalized_seed_type = str(seed_type or "").strip()
            normalized_seed_value = str(seed_value or "").strip()
            if not normalized_seed_type or not normalized_seed_value:
                continue
            key = f"{normalized_seed_type}:{normalized_seed_value}"
            counts[key] = counts.get(key, 0) + 1
        return counts

    @transaction.atomic
    def save_execution(
        self,
        execution: RecommendationExecution,
    ) -> RecommendationSnapshot:
        if execution.request.history_generation is not None:
            from .jobs import fence_history

            fence_history(execution.request.history_generation)
        snapshot = RecommendationSnapshot.objects.create(
            recommender_id=execution.recommender_id,
            strategy_id=execution.strategy_id,
            request_fingerprint=execution.request_fingerprint or "",
            request_payload={
                "limit": execution.request.limit,
                "per_seed_limit": execution.request.per_seed_limit,
                "actor_seed_limit": execution.request.actor_seed_limit,
                "genre_seed_limit": execution.request.genre_seed_limit,
                "seed_types": list(execution.request.seed_types),
                "exclude_existing": execution.request.exclude_existing,
                "random_seed": execution.request.random_seed,
                "avoid_recent_recommendations": execution.request.avoid_recent_recommendations,
                "recent_snapshot_limit": execution.request.recent_snapshot_limit,
                "recent_item_limit": execution.request.recent_item_limit,
                "include_hot_board": execution.request.include_hot_board,
                "include_latest_updates": execution.request.include_latest_updates,
                "discovery_limit": execution.request.discovery_limit,
                "detail_enrichment_limit": execution.request.detail_enrichment_limit,
                "type_preference": execution.request.type_preference,
                "actor_preference": execution.request.actor_preference,
                "genre_preference": execution.request.genre_preference,
                "force_refresh_external": execution.request.force_refresh_external,
            },
            seed_summary=[seed.to_dict() for seed in execution.run.seeds],
            item_count=len(execution.run.items),
            random_seed=execution.request.random_seed,
        )

        created_items = RecommendationItem.objects.bulk_create(
            [
                RecommendationItem(
                    snapshot=snapshot,
                    rank=index,
                    avid=item.avid,
                    title=item.title,
                    detail_url=item.detail_url,
                    cover_url=item.cover_url,
                    source=item.source,
                    score=item.total_score,
                    search_rank=item.search_rank,
                    reasons=item.reasons(),
                    matched_seeds=[seed.to_dict() for seed in item.matched_seeds],
                    score_breakdown=item.score_breakdown,
                    raw_metrics=item.raw_metrics,
                )
                for index, item in enumerate(execution.run.items, start=1)
            ]
        )
        item_seed_rows: list[RecommendationItemSeed] = []
        for item_obj, runtime_item in zip(
            created_items, execution.run.items, strict=False
        ):
            for seed in runtime_item.matched_seeds:
                lookup_payload = dict(seed.lookup_payload or {})
                source_name = str(lookup_payload.get("source_name", "")).strip().lower()
                source_identifier = ""
                if seed.seed_type == "actor":
                    source_identifier = str(
                        lookup_payload.get("model_slug", "")
                    ).strip()
                elif seed.seed_type == "genre":
                    source_identifier = str(
                        lookup_payload.get("genre_slug", "")
                    ).strip()
                item_seed_rows.append(
                    RecommendationItemSeed(
                        item=item_obj,
                        seed_type=seed.seed_type,
                        seed_value=seed.value,
                        normalized_value=_normalize_seed_value(seed.value),
                        seed_key=f"{seed.seed_type}:{seed.value}",
                        source=seed.source,
                        source_name=source_name,
                        source_identifier=source_identifier.lower(),
                        aliases=list(seed.aliases),
                        weight=seed.weight,
                        resource_count=max(int(seed.resource_count or 0), 0),
                        preference_score=seed.preference_score,
                    )
                )
        if item_seed_rows:
            RecommendationItemSeed.objects.bulk_create(item_seed_rows)
            recommendation_seed_profile_repository.sync_seed_profiles(
                items=RecommendationItem.objects.filter(
                    pk__in=[item.pk for item in created_items if item.pk is not None]
                ).prefetch_related("item_seeds"),
                timestamp=snapshot.generated_at,
            )
        return snapshot

    @transaction.atomic
    def reset_state(self, *, preserve_blocklist: bool = True) -> dict[str, int | bool]:
        from nassav.recommendation_models import RecommendationJob, RecommendationState
        from .jobs import history_generation

        history_generation()
        RecommendationState.objects.filter(pk=1).update(generation=F("generation") + 1)
        RecommendationJob.objects.filter(state__in=["queued", "running"]).update(
            state="cancelled",
            message="推荐历史已重置",
            version=F("version") + 1,
            updated_at=timezone.now(),
        )
        blocklist_count = RecommendationAvidBlocklist.objects.count()
        feedback_count = RecommendationFeedback.objects.count()
        item_seed_count = RecommendationItemSeed.objects.count()
        item_count = RecommendationItem.objects.count()
        seed_profile_count = RecommendationSeedProfile.objects.count()
        snapshot_count = RecommendationSnapshot.objects.count()
        if preserve_blocklist:
            RecommendationSeedProfile.objects.filter(is_blocked=False).delete()
            RecommendationSeedProfile.objects.filter(is_blocked=True).update(
                recommended_count=0,
                accepted_count=0,
                disliked_count=0,
                last_recommended_at=None,
            )
        else:
            RecommendationAvidBlocklist.objects.all().delete()
            RecommendationSeedProfile.objects.all().delete()
        RecommendationSnapshot.objects.all().delete()
        return {
            "preserve_blocklist": preserve_blocklist,
            "blocklist_count": blocklist_count,
            "feedback_count": feedback_count,
            "item_seed_count": item_seed_count,
            "item_count": item_count,
            "seed_profile_count": seed_profile_count,
            "snapshot_count": snapshot_count,
        }

    def build_metrics(self) -> dict:
        snapshot_count = RecommendationSnapshot.objects.count()
        item_count = RecommendationItem.objects.count()
        distinct_avid_count = (
            RecommendationItem.objects.values("avid").distinct().count()
        )
        repeated_avid_count = max(item_count - distinct_avid_count, 0)
        feedback_counts = {
            row["feedback"]: row["count"]
            for row in RecommendationFeedback.objects.values("feedback").annotate(
                count=Count("id")
            )
        }
        item_counts = list(
            RecommendationSnapshot.objects.order_by("-generated_at").values_list(
                "item_count", flat=True
            )[:50]
        )
        average_item_count = (
            round(sum(item_counts) / len(item_counts), 2) if item_counts else 0.0
        )
        top_seeds = list(
            RecommendationItemSeed.objects.values("seed_type", "seed_value")
            .annotate(count=Count("id"))
            .order_by("-count", "seed_type", "seed_value")[:20]
        )

        return {
            "snapshot_count": snapshot_count,
            "item_count": item_count,
            "distinct_avid_count": distinct_avid_count,
            "repeated_avid_count": repeated_avid_count,
            "repeat_rate": round(repeated_avid_count / item_count, 4)
            if item_count
            else 0.0,
            "average_item_count_recent_50": average_item_count,
            "feedback_count": sum(feedback_counts.values()),
            "feedback_counts": {
                "like": int(feedback_counts.get("like", 0)),
                "dislike": int(feedback_counts.get("dislike", 0)),
            },
            "avid_blocklist_count": RecommendationAvidBlocklist.objects.count(),
            "blocked_seed_count": RecommendationSeedProfile.objects.filter(
                is_blocked=True
            ).count(),
            "learned_seed_count": RecommendationSeedProfile.objects.filter(
                Q(accepted_count__gt=0) | Q(disliked_count__gt=0)
            ).count(),
            "top_seed_exposures": [
                {
                    "seed_type": row["seed_type"],
                    "seed_value": row["seed_value"],
                    "count": row["count"],
                }
                for row in top_seeds
            ],
        }


recommendation_snapshot_repository = RecommendationSnapshotRepository()


def _normalize_seed_value(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()
