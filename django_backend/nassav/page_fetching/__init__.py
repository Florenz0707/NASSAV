"""Page fetching contracts and construction helpers."""

from .contracts import BrowserPageClient, FetchFailure, PageResult
from .factory import (
    BrowserFetchConfig,
    create_page_fetch_service,
    normalize_config,
    validate_strategy,
)
from .service import PageFetchService

__all__ = [
    "BrowserFetchConfig",
    "BrowserPageClient",
    "FetchFailure",
    "PageFetchService",
    "PageResult",
    "create_page_fetch_service",
    "normalize_config",
    "validate_strategy",
]
