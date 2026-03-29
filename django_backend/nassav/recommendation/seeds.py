from abc import ABC, abstractmethod
from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone

from nassav.models import Actor, Genre

from .entities import RecommendationRequest, RecommendationSeed


class SeedProvider(ABC):
    @abstractmethod
    def get_seeds(self, request: RecommendationRequest) -> list[RecommendationSeed]:
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

    def _build_seed_batch(
        self,
        request: RecommendationRequest,
        *,
        only_interacted: bool,
    ) -> list[RecommendationSeed]:
        seeds: list[RecommendationSeed] = []

        if "actor" in request.seed_types:
            seeds.extend(
                self.get_top_actor_seeds(
                    request.actor_seed_limit,
                    only_interacted=only_interacted,
                )
            )
        if "genre" in request.seed_types:
            seeds.extend(
                self.get_top_genre_seeds(
                    request.genre_seed_limit,
                    only_interacted=only_interacted,
                )
            )

        return seeds

    def get_top_actor_seeds(
        self,
        limit: int,
        *,
        only_interacted: bool = False,
    ) -> list[RecommendationSeed]:
        queryset = self._annotated_queryset(
            Actor.objects, only_interacted=only_interacted
        )
        return self._build_seeds(
            queryset=queryset[:limit],
            seed_type="actor",
            source="local_interacted_actor" if only_interacted else "local_top_actor",
        )

    def get_top_genre_seeds(
        self,
        limit: int,
        *,
        only_interacted: bool = False,
    ) -> list[RecommendationSeed]:
        queryset = self._annotated_queryset(
            Genre.objects, only_interacted=only_interacted
        )
        return self._build_seeds(
            queryset=queryset[:limit],
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
            seeds.append(
                RecommendationSeed(
                    seed_type=seed_type,
                    value=item.name,
                    weight=self.normalize_weight(preference_score, max_score),
                    source=source,
                    resource_count=resource_count,
                    preference_score=round(preference_score, 4),
                )
            )
        return seeds

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
