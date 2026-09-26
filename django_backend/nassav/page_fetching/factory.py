"""Normalize browser configuration and create one page service per Source."""

from dataclasses import dataclass
from urllib.parse import urlparse

from loguru import logger

from .browser import ByparrPageClient, FlareSolverrPageClient
from .service import PageFetchService


@dataclass(frozen=True)
class BrowserFetchConfig:
    enabled: bool
    provider: str
    url: str
    timeout_ms: int


def normalize_config(config: dict) -> BrowserFetchConfig:
    if "BrowserFetch" in config:
        raw = config["BrowserFetch"]
        if not isinstance(raw, dict):
            raise ValueError("BrowserFetch config must be a mapping")
        if "FlareSolverr" in config:
            logger.warning(
                "FlareSolverr config is deprecated; BrowserFetch takes precedence"
            )
        provider = raw.get("provider", "byparr")
        url = raw.get("url", "http://127.0.0.1:8192")
        timeout_ms = raw.get("timeout_ms", 60000)
    else:
        raw = config.get("FlareSolverr") or {}
        if not isinstance(raw, dict):
            raise ValueError("FlareSolverr config must be a mapping")
        provider = "flaresolverr"
        url = raw.get("url", "http://localhost:8191")
        timeout_ms = raw.get("timeout", 60000)
    enabled = raw.get("Enable", False)
    if not isinstance(enabled, bool):
        raise ValueError("Browser fetch Enable must be a boolean")
    if provider not in {"byparr", "flaresolverr"}:
        raise ValueError(f"Unknown browser fetch provider: {provider}")
    parsed = urlparse(url) if isinstance(url, str) else None
    if not parsed or parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Browser fetch url must be an absolute HTTP(S) URL")
    try:
        port = parsed.port
    except ValueError as error:
        raise ValueError("Browser fetch url has an invalid port") from error
    if port is not None and port <= 0:
        raise ValueError("Browser fetch url has an invalid port")
    if (
        parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            "Browser fetch url must contain only a scheme, host, and optional port"
        )
    if (
        isinstance(timeout_ms, bool)
        or not isinstance(timeout_ms, int)
        or timeout_ms < 1000
        or timeout_ms % 1000
    ):
        raise ValueError(
            "Browser fetch timeout_ms must be whole seconds of at least 1000 ms"
        )
    return BrowserFetchConfig(enabled, provider, url.rstrip("/"), timeout_ms)


def validate_strategy(value: str) -> str:
    if value not in {"browser_first", "direct_first", "direct_only"}:
        raise ValueError(f"Unknown page fetch strategy: {value}")
    return value


def create_page_fetch_service(config: BrowserFetchConfig) -> PageFetchService:
    browser = None
    if config.enabled:
        client_class = (
            ByparrPageClient if config.provider == "byparr" else FlareSolverrPageClient
        )
        browser = client_class(config.url)
    return PageFetchService(browser, config.timeout_ms)
