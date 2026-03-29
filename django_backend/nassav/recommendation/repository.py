import json
import secrets
from hashlib import sha256

from django.db import transaction

from nassav.models import RecommendationItem, RecommendationSnapshot

from .entities import RecommendationExecution, RecommendationRequest


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

    @transaction.atomic
    def save_execution(
        self,
        execution: RecommendationExecution,
    ) -> RecommendationSnapshot:
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
            },
            seed_summary=[seed.to_dict() for seed in execution.run.seeds],
            item_count=len(execution.run.items),
            random_seed=execution.request.random_seed,
        )

        RecommendationItem.objects.bulk_create(
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
        return snapshot


recommendation_snapshot_repository = RecommendationSnapshotRepository()
