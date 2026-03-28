from abc import ABC, abstractmethod

from django.db.models import Count

from nassav.models import Actor, Genre

from .entities import RecommendationRequest, RecommendationSeed


class SeedProvider(ABC):
    @abstractmethod
    def get_seeds(self, request: RecommendationRequest) -> list[RecommendationSeed]:
        raise NotImplementedError


class LocalPreferenceSeedProvider(SeedProvider):
    def get_seeds(self, request: RecommendationRequest) -> list[RecommendationSeed]:
        seeds: list[RecommendationSeed] = []

        if "actor" in request.seed_types:
            seeds.extend(self.get_top_actor_seeds(request.actor_seed_limit))
        if "genre" in request.seed_types:
            seeds.extend(self.get_top_genre_seeds(request.genre_seed_limit))

        return seeds

    def get_top_actor_seeds(self, limit: int) -> list[RecommendationSeed]:
        queryset = (
            Actor.objects.annotate(resource_count=Count("resources"))
            .filter(resource_count__gt=0)
            .order_by("-resource_count", "name")[:limit]
        )
        return self._build_seeds(
            queryset=list(queryset),
            seed_type="actor",
            source="local_top_actor",
        )

    def get_top_genre_seeds(self, limit: int) -> list[RecommendationSeed]:
        queryset = (
            Genre.objects.annotate(resource_count=Count("resources"))
            .filter(resource_count__gt=0)
            .order_by("-resource_count", "name")[:limit]
        )
        return self._build_seeds(
            queryset=list(queryset),
            seed_type="genre",
            source="local_top_genre",
        )

    def _build_seeds(
        self, queryset, seed_type: str, source: str
    ) -> list[RecommendationSeed]:
        if not queryset:
            return []

        max_count = max(getattr(item, "resource_count", 0) for item in queryset) or 1
        seeds: list[RecommendationSeed] = []
        for item in queryset:
            resource_count = int(getattr(item, "resource_count", 0))
            weight = self.normalize_weight(resource_count, max_count)
            seeds.append(
                RecommendationSeed(
                    seed_type=seed_type,
                    value=item.name,
                    weight=weight,
                    source=source,
                    resource_count=resource_count,
                )
            )
        return seeds

    def normalize_weight(self, count: int, max_count: int) -> float:
        if max_count <= 0:
            return 0.0
        return round((count / max_count) * 5.0, 4)
