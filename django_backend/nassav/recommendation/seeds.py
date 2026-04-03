from abc import ABC, abstractmethod
from datetime import timedelta
import re
from typing import cast

from django.db.models import Count, Q
from django.utils import timezone

from nassav.models import Actor, ActorSourceMapping, Genre, GenreSourceMapping

from .actor_source_mapping import actor_source_mapping_service
from .genre_source_mapping import genre_source_mapping_service
from .entities import RecommendationRequest, RecommendationSeed
from .seed_profiles import recommendation_seed_profile_repository

USE_REQUEST_LIMIT = object()


class SeedProvider(ABC):
    @abstractmethod
    def get_seeds(self, request: RecommendationRequest) -> list[RecommendationSeed]:
        raise NotImplementedError

    @abstractmethod
    def get_additional_seeds(
        self,
        request: RecommendationRequest,
        *,
        used_seeds: list[RecommendationSeed],
        batch_size: int,
    ) -> list[RecommendationSeed]:
        raise NotImplementedError


class LocalPreferenceSeedProvider(SeedProvider):
    TIER_QUOTAS = {
        "familiar": {"high": 0.58, "mid": 0.27, "low": 0.15},
        "balanced": {"high": 0.34, "mid": 0.33, "low": 0.33},
        "rare": {"high": 0.16, "mid": 0.38, "low": 0.46},
    }

    def __init__(
        self,
        *,
        base_weight: float = 1.0,
        watched_boost: float = 0.5,
        favorite_boost: float = 1.0,
        recent_boost: float = 0.75,
        recent_days: int = 180,
        only_interacted: bool = False,
        fallback_to_all: bool = True,
    ):
        self.base_weight = base_weight
        self.watched_boost = watched_boost
        self.favorite_boost = favorite_boost
        self.recent_boost = recent_boost
        self.recent_days = recent_days
        self.only_interacted = only_interacted
        self.fallback_to_all = fallback_to_all

    def get_seeds(self, request: RecommendationRequest) -> list[RecommendationSeed]:
        seeds = self._build_seed_batch(request, only_interacted=self.only_interacted)
        seeds = recommendation_seed_profile_repository.filter_allowed_seeds(seeds)
        if seeds or not self.only_interacted or not self.fallback_to_all:
            return seeds
        fallback_seeds = self._build_seed_batch(request, only_interacted=False)
        return recommendation_seed_profile_repository.filter_allowed_seeds(
            fallback_seeds
        )

    def get_additional_seeds(
        self,
        request: RecommendationRequest,
        *,
        used_seeds: list[RecommendationSeed],
        batch_size: int,
    ) -> list[RecommendationSeed]:
        if batch_size <= 0:
            return []

        seed_pool = self._build_seed_batch(
            request,
            only_interacted=self.only_interacted,
            actor_limit=None,
            genre_limit=None,
        )
        if not seed_pool and self.only_interacted and self.fallback_to_all:
            seed_pool = self._build_seed_batch(
                request,
                only_interacted=False,
                actor_limit=None,
                genre_limit=None,
            )
        seed_pool = recommendation_seed_profile_repository.filter_allowed_seeds(
            seed_pool
        )

        used_keys = {(seed.seed_type, seed.value) for seed in used_seeds}
        extras: list[RecommendationSeed] = []
        for seed in seed_pool:
            key = (seed.seed_type, seed.value)
            if key in used_keys:
                continue
            extras.append(self._to_expansion_seed(seed))
            if len(extras) >= batch_size:
                break
        return extras

    def _build_seed_batch(
        self,
        request: RecommendationRequest,
        *,
        only_interacted: bool,
        actor_limit: int | None | object = USE_REQUEST_LIMIT,
        genre_limit: int | None | object = USE_REQUEST_LIMIT,
    ) -> list[RecommendationSeed]:
        seeds: list[RecommendationSeed] = []
        resolved_actor_limit: int | None
        if actor_limit is USE_REQUEST_LIMIT:
            resolved_actor_limit = request.actor_seed_limit
        else:
            resolved_actor_limit = cast(int | None, actor_limit)

        resolved_genre_limit: int | None
        if genre_limit is USE_REQUEST_LIMIT:
            resolved_genre_limit = request.genre_seed_limit
        else:
            resolved_genre_limit = cast(int | None, genre_limit)

        if "actor" in request.seed_types:
            seeds.extend(
                self.get_top_actor_seeds(
                    resolved_actor_limit,
                    only_interacted=only_interacted,
                    request=request,
                )
            )
        if "genre" in request.seed_types:
            seeds.extend(
                self.get_top_genre_seeds(
                    resolved_genre_limit,
                    only_interacted=only_interacted,
                    request=request,
                )
            )

        return seeds

    def get_top_actor_seeds(
        self,
        limit: int | None,
        *,
        only_interacted: bool = False,
        request: RecommendationRequest | None = None,
    ) -> list[RecommendationSeed]:
        queryset = self._annotated_queryset(
            Actor.objects, only_interacted=only_interacted
        )
        seeds = self._build_seeds(
            queryset=queryset,
            seed_type="actor",
            source="local_interacted_actor" if only_interacted else "local_top_actor",
        )
        return self._select_seed_subset(
            seeds=seeds,
            limit=limit,
            request=request,
            seed_type="actor",
        )

    def get_top_genre_seeds(
        self,
        limit: int | None,
        *,
        only_interacted: bool = False,
        request: RecommendationRequest | None = None,
    ) -> list[RecommendationSeed]:
        queryset = self._annotated_queryset(
            Genre.objects, only_interacted=only_interacted
        )
        seeds = self._build_seeds(
            queryset=queryset,
            seed_type="genre",
            source="local_interacted_genre" if only_interacted else "local_top_genre",
        )
        return self._select_seed_subset(
            seeds=seeds,
            limit=limit,
            request=request,
            seed_type="genre",
        )

    def _select_seed_subset(
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

    def _annotated_queryset(self, manager, *, only_interacted: bool = False) -> list:
        recent_since = timezone.now() - timedelta(days=max(self.recent_days, 1))
        interaction_filter = Q(resources__watched=True) | Q(resources__is_favorite=True)
        queryset = manager.annotate(
            resource_count=Count("resources", distinct=True),
            watched_count=Count(
                "resources",
                filter=Q(resources__watched=True),
                distinct=True,
            ),
            favorite_count=Count(
                "resources",
                filter=Q(resources__is_favorite=True),
                distinct=True,
            ),
            recent_count=Count(
                "resources",
                filter=Q(resources__created_at__gte=recent_since),
                distinct=True,
            ),
            interacted_count=Count(
                "resources",
                filter=interaction_filter,
                distinct=True,
            ),
        ).filter(resource_count__gt=0)
        if only_interacted:
            queryset = queryset.filter(interacted_count__gt=0)

        return sorted(
            queryset,
            key=lambda item: (
                -self.preference_score_for_item(item),
                -int(getattr(item, "resource_count", 0) or 0),
                getattr(item, "name", ""),
            ),
        )

    def _build_seeds(
        self, queryset: list, seed_type: str, source: str
    ) -> list[RecommendationSeed]:
        if not queryset:
            return []

        if seed_type == "actor":
            return self._build_actor_seeds(queryset=queryset, source=source)
        if seed_type == "genre":
            return self._build_genre_seeds(queryset=queryset, source=source)

        max_score = (
            max(self.preference_score_for_item(item) for item in queryset) or 1.0
        )
        seeds: list[RecommendationSeed] = []
        for item in queryset:
            resource_count = int(getattr(item, "resource_count", 0) or 0)
            preference_score = self.preference_score_for_item(item)
            aliases = self._build_seed_aliases(seed_type=seed_type, value=item.name)
            seeds.append(
                RecommendationSeed(
                    seed_type=seed_type,
                    value=item.name,
                    weight=self.normalize_weight(preference_score, max_score),
                    source=source,
                    aliases=aliases,
                    resource_count=resource_count,
                    preference_score=round(preference_score, 4),
                )
            )
        return seeds

    def _build_genre_seeds(
        self,
        *,
        queryset: list[Genre],
        source: str,
    ) -> list[RecommendationSeed]:
        if not queryset:
            return []

        mappings = genre_source_mapping_service.get_genre_source_mappings(
            genre_ids=[item.pk for item in queryset if item.pk is not None],
            source_name="jable",
        )
        max_score = (
            max(self.preference_score_for_item(item) for item in queryset) or 1.0
        )
        seeds: list[RecommendationSeed] = []
        for item in queryset:
            resource_count = int(getattr(item, "resource_count", 0) or 0)
            preference_score = self.preference_score_for_item(item)
            mapping = mappings.get(int(item.pk)) if item.pk is not None else None
            seeds.append(
                RecommendationSeed(
                    seed_type="genre",
                    value=item.name,
                    weight=self.normalize_weight(preference_score, max_score),
                    source=source,
                    lookup_payload=self._build_genre_lookup_payload(mapping),
                    resource_count=resource_count,
                    preference_score=round(preference_score, 4),
                )
            )
        return seeds

    def _build_actor_seeds(
        self,
        *,
        queryset: list[Actor],
        source: str,
    ) -> list[RecommendationSeed]:
        if not queryset:
            return []

        mappings = actor_source_mapping_service.get_actor_source_mappings(
            actor_ids=[item.pk for item in queryset if item.pk is not None],
            source_name="jable",
        )
        max_score = (
            max(self.preference_score_for_item(item) for item in queryset) or 1.0
        )
        seeds: list[RecommendationSeed] = []
        for item in queryset:
            resource_count = int(getattr(item, "resource_count", 0) or 0)
            preference_score = self.preference_score_for_item(item)
            mapping = mappings.get(int(item.pk)) if item.pk is not None else None
            aliases = self._build_actor_seed_aliases(value=item.name, mapping=mapping)
            seeds.append(
                RecommendationSeed(
                    seed_type="actor",
                    value=item.name,
                    weight=self.normalize_weight(preference_score, max_score),
                    source=source,
                    aliases=aliases,
                    lookup_payload=self._build_actor_lookup_payload(mapping),
                    resource_count=resource_count,
                    preference_score=round(preference_score, 4),
                )
            )
        return seeds

    def _build_seed_aliases(self, *, seed_type: str, value: str) -> list[str]:
        if seed_type != "actor":
            return []
        return self._extract_actor_aliases(value)

    def _build_actor_seed_aliases(
        self,
        *,
        value: str,
        mapping: ActorSourceMapping | None,
    ) -> list[str]:
        aliases = self._extract_actor_aliases(value)
        seen = {value.casefold(), *(alias.casefold() for alias in aliases)}

        def add_alias(candidate: str) -> None:
            normalized = str(candidate or "").strip()
            if not normalized:
                return
            token = normalized.casefold()
            if token in seen:
                return
            seen.add(token)
            aliases.append(normalized)

        if mapping is not None:
            add_alias(mapping.source_actor_name)
            for candidate in mapping.aliases or []:
                add_alias(str(candidate))

        return aliases

    def _build_actor_lookup_payload(
        self,
        mapping: ActorSourceMapping | None,
    ) -> dict:
        if mapping is None or not mapping.source_actor_slug:
            return {}

        payload = {
            "source_name": mapping.source_name,
            "model_slug": mapping.source_actor_slug,
        }
        if mapping.source_actor_name:
            payload["source_actor_name"] = mapping.source_actor_name
        if mapping.source_actor_url:
            payload["source_actor_url"] = mapping.source_actor_url
        return payload

    def _build_genre_lookup_payload(
        self,
        mapping: GenreSourceMapping | None,
    ) -> dict:
        if mapping is None or not mapping.source_genre_slug:
            return {}

        payload = {
            "source_name": mapping.source_name,
            "genre_slug": mapping.source_genre_slug,
        }
        if mapping.source_genre_name:
            payload["source_genre_name"] = mapping.source_genre_name
        if mapping.source_genre_url:
            payload["source_genre_url"] = mapping.source_genre_url
            if "/categories/" in mapping.source_genre_url:
                payload["genre_taxonomy"] = "category"
            elif "/tags/" in mapping.source_genre_url:
                payload["genre_taxonomy"] = "tag"
        return payload

    def _extract_actor_aliases(self, raw_name: str) -> list[str]:
        name = str(raw_name or "").strip()
        if not name:
            return []

        variants: list[str] = []
        seen: set[str] = {name.casefold()}

        def add_variant(candidate: str) -> None:
            normalized = str(candidate or "").strip()
            if not normalized:
                return
            token = normalized.casefold()
            if token in seen:
                return
            seen.add(token)
            variants.append(normalized)

        fullwidth_match = re.match(r"^(.*?)（(.+?)）$", name)
        halfwidth_match = re.match(r"^(.*?)\((.+?)\)$", name)
        match = fullwidth_match or halfwidth_match
        if match:
            outer_name = match.group(1).strip()
            inner_aliases = match.group(2).strip()
            add_variant(outer_name)
            for part in re.split(r"[、,，/／|・]+", inner_aliases):
                add_variant(part)

        compact = re.sub(r"\s+", " ", name).strip()
        if compact != name:
            add_variant(compact)

        return variants

    def _to_expansion_seed(self, seed: RecommendationSeed) -> RecommendationSeed:
        source = seed.source
        if source.startswith("local_top_"):
            source = source.replace("local_top_", "local_expansion_", 1)
        elif source.startswith("local_interacted_"):
            source = source.replace("local_interacted_", "local_expansion_", 1)

        return RecommendationSeed(
            seed_type=seed.seed_type,
            value=seed.value,
            weight=seed.weight,
            source=source,
            aliases=list(seed.aliases),
            lookup_payload=dict(seed.lookup_payload),
            resource_count=seed.resource_count,
            preference_score=seed.preference_score,
        )

    def preference_score_for_item(self, item) -> float:
        resource_count = float(getattr(item, "resource_count", 0) or 0)
        watched_count = float(getattr(item, "watched_count", 0) or 0)
        favorite_count = float(getattr(item, "favorite_count", 0) or 0)
        recent_count = float(getattr(item, "recent_count", 0) or 0)
        return (
            resource_count * self.base_weight
            + watched_count * self.watched_boost
            + favorite_count * self.favorite_boost
            + recent_count * self.recent_boost
        )

    def normalize_weight(self, count: float, max_count: float) -> float:
        if max_count <= 0:
            return 0.0
        return round((count / max_count) * 5.0, 4)
