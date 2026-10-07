"""Normalize browser configuration and create one page service per Source."""

from dataclasses import dataclass
from contextlib import contextmanager
from urllib.parse import urlparse

from loguru import logger

from .browser import ByparrPageClient, FlareSolverrPageClient
from .service import PageFetchService
from .proxy_server import OrderedProxyServer, ProxyServer


@dataclass(frozen=True)
class BrowserFetchConfig:
    enabled: bool
    provider: str
    url: str
    timeout_ms: int
    session_reuse_enabled: bool = False
    max_concurrency: int = 2


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
    if not isinstance(provider, str) or provider not in {"byparr", "flaresolverr"}:
        raise ValueError("BrowserFetch.provider must be byparr or flaresolverr")
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
    session_reuse_enabled = raw.get("session_reuse_enabled", False)
    if not isinstance(session_reuse_enabled, bool):
        raise ValueError("BrowserFetch.session_reuse_enabled must be a boolean")
    max_concurrency = raw.get("max_concurrency", 2 if "BrowserFetch" in config else 1)
    if (
        isinstance(max_concurrency, bool)
        or not isinstance(max_concurrency, int)
        or not 1 <= max_concurrency <= 8
    ):
        raise ValueError("BrowserFetch.max_concurrency must be an integer from 1 to 8")
    return BrowserFetchConfig(
        enabled,
        provider,
        url.rstrip("/"),
        timeout_ms,
        session_reuse_enabled,
        max_concurrency,
    )


def validate_strategy(value: str) -> str:
    if not isinstance(value, str) or value not in {
        "browser_first",
        "direct_first",
        "direct_only",
    }:
        raise ValueError(
            "browser_fetch_strategy must be browser_first, direct_first, or direct_only"
        )
    return value


def create_page_fetch_service(
    config: BrowserFetchConfig,
    *,
    proxy_url: str | None = None,
    proxy_server: ProxyServer | None = None,
) -> PageFetchService:
    browser = None
    if config.enabled:
        if config.provider == "byparr":
            browser = ByparrPageClient(config.url, proxy_url=proxy_url)
        else:
            browser = FlareSolverrPageClient(config.url)
        from .proxy_client import ProxyPageClient

        browser = ProxyPageClient(browser, proxy_server or create_proxy_server(config))
    return PageFetchService(
        browser, config.timeout_ms, session_reuse_enabled=config.session_reuse_enabled
    )


def create_proxy_server(config: BrowserFetchConfig) -> ProxyServer:
    """Production capacity is shared across processes, never provider-specific."""
    if not config.enabled:
        return OrderedProxyServer()
    import redis
    from django.conf import settings
    from .proxy_capacity import RedisProxyCapacity

    client = redis.from_url(
        settings.CELERY_BROKER_URL, socket_timeout=2, socket_connect_timeout=2
    )
    return OrderedProxyServer(
        config.max_concurrency,
        capacity=RedisProxyCapacity(client, config.url, config.max_concurrency),
        worker_scope=_worker_connections,
    )


@contextmanager
def _worker_connections():
    """Django connections are thread-local, including ownership check queries."""
    from django.db import close_old_connections, connections

    close_old_connections()
    try:
        yield
    finally:
        connections.close_all()
