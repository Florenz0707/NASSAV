"""Capabilities for recommendation inventory, context and source recall."""

from abc import ABC, abstractmethod
from .entities import RecommendationRequest, RecommendationExecution, RecommendationSeed


class CandidateInventory(ABC):
    @abstractmethod
    def existing(self, avids: set[str]) -> set[str]: ...


class RecommendationContextStore(ABC):
    @abstractmethod
    def next_random_seed(self) -> int: ...
    @abstractmethod
    def prepare(
        self, request: RecommendationRequest, recommender_id: str, strategy_id: str
    ) -> str: ...
    @abstractmethod
    def persist(self, execution: RecommendationExecution) -> int | None: ...


class RecommendationSource(ABC):
    @abstractmethod
    def search(
        self, keyword: str, page: int = 1, *, force_refresh: bool = False
    ) -> list[dict]: ...
    @abstractmethod
    def get_model_videos(
        self,
        model_slug: str,
        page: int = 1,
        sort_by: str = "video_viewed",
        *,
        force_refresh: bool = False,
    ) -> list[dict]: ...
    @abstractmethod
    def get_category_videos(
        self, category_slug: str, page: int = 1, *, force_refresh: bool = False
    ) -> list[dict]: ...
    @abstractmethod
    def get_tag_videos(
        self, tag_slug: str, page: int = 1, *, force_refresh: bool = False
    ) -> list[dict]: ...
    @abstractmethod
    def discover_hot_items(
        self, page: int = 1, *, force_refresh: bool = False
    ) -> list[dict]: ...
    @abstractmethod
    def discover_latest_updates(
        self, page: int = 1, *, force_refresh: bool = False
    ) -> list[dict]: ...
    @abstractmethod
    def get_video_detail(
        self, avid: str, detail_url: str = "", *, force_refresh: bool = False
    ) -> dict: ...


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


class RecommendationWorkflow(ABC):
    @abstractmethod
    def recommend(
        self,
        recommender_id: str | None = None,
        strategy_id: str | None = None,
        request_params: dict | None = None,
    ) -> RecommendationExecution: ...
    @abstractmethod
    def get_options(self) -> dict: ...
