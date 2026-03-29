from abc import ABC, abstractmethod
from datetime import timedelta
import re
from typing import cast

from django.db.models import Count, Q
from django.utils import timezone

from nassav.models import Actor, Genre

from .entities import RecommendationRequest, RecommendationSeed

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
        if seeds or not self.only_interacted or not self.fallback_to_all:
            return seeds
        return self._build_seed_batch(request, only_interacted=False)

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
                )
            )
        if "genre" in request.seed_types:
            seeds.extend(
                self.get_top_genre_seeds(
                    resolved_genre_limit,
                    only_interacted=only_interacted,
                )
            )

        return seeds

    def get_top_actor_seeds(
        self,
        limit: int | None,
        *,
        only_interacted: bool = False,
    ) -> list[RecommendationSeed]:
        queryset = self._annotated_queryset(
            Actor.objects, only_interacted=only_interacted
        )
        if limit is not None and limit > 0:
            queryset = queryset[:limit]
        return self._build_seeds(
            queryset=queryset,
            seed_type="actor",
            source="local_interacted_actor" if only_interacted else "local_top_actor",
        )

    def get_top_genre_seeds(
        self,
        limit: int | None,
        *,
        only_interacted: bool = False,
    ) -> list[RecommendationSeed]:
        queryset = self._annotated_queryset(
            Genre.objects, only_interacted=only_interacted
        )
        if limit is not None and limit > 0:
            queryset = queryset[:limit]
        return self._build_seeds(
            queryset=queryset,
            seed_type="genre",
            source="local_interacted_genre" if only_interacted else "local_top_genre",
        )

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

    def _build_seed_aliases(self, *, seed_type: str, value: str) -> list[str]:
        if seed_type != "actor":
            return []
        return self._extract_actor_aliases(value)

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
