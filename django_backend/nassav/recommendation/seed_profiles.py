import re
from collections.abc import Iterable

from django.db.models import F
from django.utils import timezone

from nassav.models import RecommendationItem, RecommendationSeedProfile

from .entities import RecommendationSeed


class RecommendationSeedProfileRepository:
    def filter_allowed_seeds(
        self,
        seeds: list[RecommendationSeed],
    ) -> list[RecommendationSeed]:
        if not seeds:
            return []

        blocked_profiles = list(
            RecommendationSeedProfile.objects.filter(is_blocked=True).only(
                "seed_type",
                "normalized_value",
                "source_name",
                "source_identifier",
            )
        )
        if not blocked_profiles:
            return seeds

        blocked_name_keys = {
            (profile.seed_type, profile.normalized_value)
            for profile in blocked_profiles
            if profile.normalized_value
        }
        blocked_source_keys = {
            (profile.seed_type, profile.source_name, profile.source_identifier)
            for profile in blocked_profiles
            if profile.source_name and profile.source_identifier
        }

        allowed: list[RecommendationSeed] = []
        for seed in seeds:
            normalized_value = self.normalize_value(seed.value)
            lookup_payload = dict(seed.lookup_payload or {})
            source_name = str(lookup_payload.get("source_name", "")).strip().lower()
            source_identifier = self._source_identifier_for_seed(seed)

            if (seed.seed_type, normalized_value) in blocked_name_keys:
                continue
            if source_name and source_identifier:
                if (
                    seed.seed_type,
                    source_name,
                    source_identifier,
                ) in blocked_source_keys:
                    continue
            allowed.append(seed)
        return allowed

    def sync_seed_profiles(
        self,
        *,
        items: Iterable[RecommendationItem],
        timestamp=None,
    ) -> None:
        timestamp = timestamp or timezone.now()
        grouped: dict[tuple[str, str, str, str], dict] = {}
        for item in items:
            seed_rows = getattr(item, "item_seeds").all()
            for seed_row in seed_rows:
                identity = (
                    seed_row.seed_type,
                    seed_row.normalized_value,
                    seed_row.source_name,
                    seed_row.source_identifier,
                )
                payload = grouped.setdefault(
                    identity,
                    {
                        "seed_type": seed_row.seed_type,
                        "value": seed_row.seed_value,
                        "source_name": seed_row.source_name,
                        "source_identifier": seed_row.source_identifier,
                        "aliases": list(seed_row.aliases or []),
                        "recommended_count": 0,
                    },
                )
                payload["recommended_count"] += 1
                if not payload["value"] and seed_row.seed_value:
                    payload["value"] = seed_row.seed_value
                payload["aliases"] = self._merge_aliases(
                    payload["aliases"],
                    list(seed_row.aliases or []),
                )

        for identity, payload in grouped.items():
            profile, created = RecommendationSeedProfile.objects.get_or_create(
                seed_type=identity[0],
                normalized_value=identity[1],
                source_name=identity[2],
                source_identifier=identity[3],
                defaults={
                    "value": payload["value"],
                    "aliases": payload["aliases"],
                    "recommended_count": payload["recommended_count"],
                    "last_recommended_at": timestamp,
                },
            )
            if created:
                continue

            profile.value = profile.value or payload["value"]
            profile.aliases = self._merge_aliases(
                list(profile.aliases or []),
                payload["aliases"],
            )
            profile.last_recommended_at = timestamp
            RecommendationSeedProfile.objects.filter(pk=profile.pk).update(
                value=profile.value,
                aliases=profile.aliases,
                last_recommended_at=timestamp,
                recommended_count=F("recommended_count") + payload["recommended_count"],
                updated_at=timestamp,
            )

    def build_seed_score_map(self) -> dict[str, float]:
        profiles = RecommendationSeedProfile.objects.filter(
            recommended_count__gt=0
        ).only(
            "seed_type",
            "value",
            "accepted_count",
            "disliked_count",
            "recommended_count",
        )
        output: dict[str, float] = {}
        for profile in profiles:
            recommended_count = max(int(profile.recommended_count or 0), 1)
            net = int(profile.accepted_count or 0) - int(profile.disliked_count or 0)
            if net == 0:
                continue
            output[f"{profile.seed_type}:{profile.value}"] = round(
                net / recommended_count, 4
            )
        return output

    def increment_dislike_counts_for_item(self, item: RecommendationItem) -> None:
        seen_profiles: set[tuple[str, str, str, str]] = set()
        seed_rows = getattr(item, "item_seeds").all()
        for seed_row in seed_rows:
            identity = (
                seed_row.seed_type,
                seed_row.normalized_value,
                seed_row.source_name,
                seed_row.source_identifier,
            )
            if identity in seen_profiles:
                continue
            seen_profiles.add(identity)

            profile, _ = RecommendationSeedProfile.objects.get_or_create(
                seed_type=identity[0],
                normalized_value=identity[1],
                source_name=identity[2],
                source_identifier=identity[3],
                defaults={
                    "value": seed_row.seed_value,
                    "aliases": list(seed_row.aliases or []),
                },
            )
            RecommendationSeedProfile.objects.filter(pk=profile.pk).update(
                value=profile.value or seed_row.seed_value,
                aliases=self._merge_aliases(
                    list(profile.aliases or []),
                    list(seed_row.aliases or []),
                ),
                disliked_count=F("disliked_count") + 1,
                updated_at=timezone.now(),
            )

    def _source_identifier_for_seed(self, seed: RecommendationSeed) -> str:
        payload = dict(seed.lookup_payload or {})
        if seed.seed_type == "actor":
            return str(payload.get("model_slug", "")).strip().lower()
        if seed.seed_type == "genre":
            return str(payload.get("genre_slug", "")).strip().lower()
        return ""

    def _merge_aliases(self, base: list[str], extra: list[str]) -> list[str]:
        merged: list[str] = []
        seen: set[str] = set()
        for item in [*(base or []), *(extra or [])]:
            normalized = str(item or "").strip()
            if not normalized:
                continue
            token = normalized.casefold()
            if token in seen:
                continue
            seen.add(token)
            merged.append(normalized)
        return merged

    @staticmethod
    def normalize_value(value: str) -> str:
        return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


recommendation_seed_profile_repository = RecommendationSeedProfileRepository()
