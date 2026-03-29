from dataclasses import dataclass, field


@dataclass
class RecommendationSeed:
    seed_type: str
    value: str
    weight: float
    source: str
    resource_count: int = 0
    preference_score: float = 0.0

    def to_dict(self) -> dict:
        return {
            "seed_type": self.seed_type,
            "value": self.value,
            "weight": self.weight,
            "source": self.source,
            "resource_count": self.resource_count,
            "preference_score": self.preference_score,
        }


@dataclass
class RecommendationCandidate:
    avid: str
    title: str
    detail_url: str
    cover_url: str
    source: str = "Jable"
    search_rank: int | None = None
    matched_seeds: list[RecommendationSeed] = field(default_factory=list)
    raw_metrics: dict = field(default_factory=dict)
    score_breakdown: list[dict] = field(default_factory=list)
    total_score: float = 0.0

    def add_seed(self, seed: RecommendationSeed) -> None:
        if any(
            existing.seed_type == seed.seed_type and existing.value == seed.value
            for existing in self.matched_seeds
        ):
            return
        self.matched_seeds.append(seed)

    def reasons(self) -> list[str]:
        output: list[str] = []
        for item in self.score_breakdown:
            for reason in item.get("reasons", []):
                if reason not in output:
                    output.append(reason)
        return output

    def to_dict(self) -> dict:
        return {
            "avid": self.avid,
            "title": self.title,
            "detail_url": self.detail_url,
            "cover_url": self.cover_url,
            "source": self.source,
            "search_rank": self.search_rank,
            "score": self.total_score,
            "reasons": self.reasons(),
            "matched_seeds": [seed.to_dict() for seed in self.matched_seeds],
            "score_breakdown": self.score_breakdown,
            "raw_metrics": self.raw_metrics,
        }


@dataclass
class RecommendationRequest:
    limit: int = 12
    per_seed_limit: int = 12
    actor_seed_limit: int = 5
    genre_seed_limit: int = 5
    seed_types: list[str] = field(default_factory=lambda: ["actor", "genre"])
    exclude_existing: bool = True


@dataclass
class RecommendationRun:
    seeds: list[RecommendationSeed]
    items: list[RecommendationCandidate]

    def to_dict(self) -> dict:
        return {
            "items": [item.to_dict() for item in self.items],
            "seeds": [seed.to_dict() for seed in self.seeds],
            "summary": {
                "seed_count": len(self.seeds),
                "item_count": len(self.items),
            },
        }


@dataclass
class RecommendationExecution:
    recommender_id: str
    strategy_id: str
    request: RecommendationRequest
    run: RecommendationRun
    recommender_meta: dict | None = None
    strategy_meta: dict | None = None

    def to_dict(self) -> dict:
        data = self.run.to_dict()
        data["meta"] = {
            "recommender": self.recommender_id,
            "strategy": self.strategy_id,
            "recommender_detail": self.recommender_meta,
            "strategy_detail": self.strategy_meta,
            "effective_request": {
                "limit": self.request.limit,
                "per_seed_limit": self.request.per_seed_limit,
                "actor_seed_limit": self.request.actor_seed_limit,
                "genre_seed_limit": self.request.genre_seed_limit,
                "seed_types": list(self.request.seed_types),
                "exclude_existing": self.request.exclude_existing,
            },
        }
        return data
