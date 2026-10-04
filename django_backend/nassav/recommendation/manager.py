"""Production recommendation facade for HTTP and existing synchronous callers."""

from .workflow import (
    RecommendationManagerError as RecommendationManagerError,
    RecommenderManager as RecommenderManager,
)
from nassav.composition import build_recommendation_manager

recommender_manager = build_recommendation_manager()
