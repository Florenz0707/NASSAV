from dataclasses import dataclass, field


@dataclass
class RecommendationSeed:
    seed_type: str
    value: str
    weight: float
    source: str
    aliases: list[str] = field(default_factory=list)
    resource_count: int = 0
    preference_score: float = 0.0

    def to_dict(self) -> dict:
        return {
            "seed_type": self.seed_type,
            "value": self.value,
            "weight": self.weight,
            "source": self.source,
            "aliases": list(self.aliases),
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
    snapshot_id: int | None = None
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
            "snapshot_id": self.snapshot_id,
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
    random_seed: int = 0
    avoid_recent_recommendations: bool = True
    recent_snapshot_limit: int = 3
    recent_item_limit: int = 36
    recently_recommended_avids: list[str] = field(default_factory=list)
    recent_recommendation_counts: dict[str, int] = field(default_factory=dict)
    include_hot_board: bool = True
    include_latest_updates: bool = True
    discovery_limit: int = 12
    feedback_avid_scores: dict[str, float] = field(default_factory=dict)
    feedback_seed_scores: dict[str, float] = field(default_factory=dict)
    blocked_feedback_avids: set[str] = field(default_factory=set)
    learned_feedback_count: int = 0
    learned_avid_count: int = 0
    learned_seed_count: int = 0


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
    snapshot_id: int | None = None
    request_fingerprint: str | None = None
    filtered_history_count: int = 0

    def to_dict(self) -> dict:
        data = self.run.to_dict()
        data["meta"] = {
            "recommender": self.recommender_id,
            "strategy": self.strategy_id,
            "snapshot_id": self.snapshot_id,
            "request_fingerprint": self.request_fingerprint,
            "recommender_detail": self.recommender_meta,
            "strategy_detail": self.strategy_meta,
            "effective_request": {
                "limit": self.request.limit,
                "per_seed_limit": self.request.per_seed_limit,
                "actor_seed_limit": self.request.actor_seed_limit,
                "genre_seed_limit": self.request.genre_seed_limit,
                "seed_types": list(self.request.seed_types),
                "exclude_existing": self.request.exclude_existing,
                "random_seed": self.request.random_seed,
                "avoid_recent_recommendations": self.request.avoid_recent_recommendations,
                "recent_snapshot_limit": self.request.recent_snapshot_limit,
                "recent_item_limit": self.request.recent_item_limit,
                "include_hot_board": self.request.include_hot_board,
                "include_latest_updates": self.request.include_latest_updates,
                "discovery_limit": self.request.discovery_limit,
            },
            "history_context": {
                "recently_recommended_count": len(
                    self.request.recently_recommended_avids
                ),
                "recent_history_candidate_count": len(
                    self.request.recent_recommendation_counts
                ),
                "filtered_history_count": self.filtered_history_count,
            },
            "learning_context": {
                "feedback_count": self.request.learned_feedback_count,
                "learned_avid_count": self.request.learned_avid_count,
                "learned_seed_count": self.request.learned_seed_count,
            },
        }
        return data
