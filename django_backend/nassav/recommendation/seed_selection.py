"""Pure seed-tier selection; database-backed providers supply candidates."""

from abc import ABC, abstractmethod
from .entities import RecommendationRequest, RecommendationSeed


class SeedSelector(ABC):
    @abstractmethod
    def select(
        self,
        *,
        seeds: list[RecommendationSeed],
        limit: int | None,
        request: RecommendationRequest | None,
        seed_type: str,
    ) -> list[RecommendationSeed]: ...


class PreferenceSeedSelector(SeedSelector):
    TIER_QUOTAS = {
        "familiar": {"high": 0.58, "mid": 0.27, "low": 0.15},
        "balanced": {"high": 0.34, "mid": 0.33, "low": 0.33},
        "rare": {"high": 0.16, "mid": 0.38, "low": 0.46},
    }

    def select(
        self,
        *,
        seeds: list[RecommendationSeed],
        limit: int | None,
        request: RecommendationRequest | None,
        seed_type: str,
    ) -> list[RecommendationSeed]:
        if limit is None or limit <= 0 or len(seeds) <= limit:
            return seeds

        profile_value = (
            request.actor_preference
            if (request is not None and seed_type == "actor")
            else request.genre_preference
            if request is not None
            else "balanced"
        )
        profile = str(profile_value or "balanced").strip().lower()
        quotas = self.TIER_QUOTAS.get(profile, self.TIER_QUOTAS["balanced"])

        high_bucket, mid_bucket, low_bucket = self._split_seed_tiers(seeds)
        target_counts = self._build_target_counts(limit=limit, quotas=quotas)

        selected: list[RecommendationSeed] = []
        selected.extend(
            self._pick_seeds_for_bucket(
                high_bucket,
                target_counts["high"],
                request=request,
            )
        )
        selected.extend(
            self._pick_seeds_for_bucket(
                mid_bucket,
                target_counts["mid"],
                request=request,
            )
        )
        selected.extend(
            self._pick_seeds_for_bucket(
                low_bucket,
                target_counts["low"],
                request=request,
            )
        )

        if len(selected) >= limit:
            return selected[:limit]

        used_keys = {(seed.seed_type, seed.value) for seed in selected}
        remainder = [
            seed for seed in seeds if (seed.seed_type, seed.value) not in used_keys
        ]
        remainder = sorted(
            remainder,
            key=lambda seed: (
                self._rotation_penalty(seed, request),
                -(seed.preference_score or 0),
                seed.value,
            ),
        )
        for seed in remainder:
            selected.append(seed)
            if len(selected) >= limit:
                break
        return selected

    def _split_seed_tiers(
        self,
        seeds: list[RecommendationSeed],
    ) -> tuple[
        list[RecommendationSeed], list[RecommendationSeed], list[RecommendationSeed]
    ]:
        ordered = sorted(
            seeds,
            key=lambda seed: (
                -(seed.resource_count or 0),
                -(seed.preference_score or 0),
                seed.value,
            ),
        )
        total = len(ordered)
        if total <= 0:
            return [], [], []

        high_size = max(total // 3, 1)
        low_size = max(total // 3, 1)
        low_start = max(total - low_size, high_size)
        return ordered[:high_size], ordered[high_size:low_start], ordered[low_start:]

    def _build_target_counts(
        self, *, limit: int, quotas: dict[str, float]
    ) -> dict[str, int]:
        targets = {
            "high": max(int(round(limit * quotas["high"])), 0),
            "mid": max(int(round(limit * quotas["mid"])), 0),
            "low": max(int(round(limit * quotas["low"])), 0),
        }
        total = targets["high"] + targets["mid"] + targets["low"]
        while total < limit:
            for key in ("low", "mid", "high"):
                targets[key] += 1
                total += 1
                if total >= limit:
                    break
        while total > limit:
            for key in ("high", "mid", "low"):
                if targets[key] <= 0:
                    continue
                targets[key] -= 1
                total -= 1
                if total <= limit:
                    break
        return targets

    def _pick_seeds_for_bucket(
        self,
        bucket: list[RecommendationSeed],
        count: int,
        *,
        request: RecommendationRequest | None,
    ) -> list[RecommendationSeed]:
        if count <= 0 or not bucket:
            return []
        ranked = sorted(
            bucket,
            key=lambda seed: (
                self._rotation_penalty(seed, request),
                -(seed.preference_score or 0),
                seed.value,
            ),
        )
        return ranked[:count]

    def _rotation_penalty(
        self,
        seed: RecommendationSeed,
        request: RecommendationRequest | None,
    ) -> float:
        if request is None:
            return 0.0
        key = f"{seed.seed_type}:{seed.value}"
        return float(request.recent_seed_counts.get(key, 0))
