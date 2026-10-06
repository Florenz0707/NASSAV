"""Production recommendation facade for HTTP and existing synchronous callers."""

from nassav.composition import build_recommendation_manager

from .workflow import (
    RecommendationManagerError as RecommendationManagerError,
)
from .workflow import (
    RecommenderManager as RecommenderManager,
)

recommender_manager = build_recommendation_manager()
