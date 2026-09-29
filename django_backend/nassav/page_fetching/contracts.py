"""Public contracts for fetching a page through a browser provider."""

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Protocol
from dataclasses import dataclass
from enum import StrEnum


class FetchFailure(StrEnum):
    CONNECTION = "connection"
    TIMEOUT = "timeout"
    API_HTTP = "api_http"
    INVALID_RESPONSE = "invalid_response"
    PROVIDER = "provider"
    TARGET_HTTP = "target_http"
    EMPTY = "empty"
    CHALLENGE = "challenge"
    PAGE_MISMATCH = "page_mismatch"


@dataclass(frozen=True)
class PageResult:
    html: str = ""
    final_url: str = ""
    provider: str = ""
    elapsed_ms: int = 0
    cookies: tuple[dict, ...] = ()
    user_agent: str = ""
    provider_status: int | None = None
    target_status: int | None = None
    failure: FetchFailure | None = None
    session_version: str | None = None
    lock_wait_ms: int = 0

    @property
    def ok(self) -> bool:
        return self.failure is None and bool(self.html)


class BrowserPageClient(ABC):
    """Fetch a raw browser page without deciding whether it is a business page."""

    @abstractmethod
    def fetch(self, url: str, *, timeout_ms: int) -> PageResult:
        raise NotImplementedError


class BrowserSessionHandler(Protocol):
    """Source-owned hooks for committing and coordinating browser sessions."""

    def browser_session_version(self) -> str | None: ...

    def accept_browser_session(
        self,
        url: str,
        result: PageResult,
        validator: Callable[[str], bool],
        expected_version: str | None,
    ) -> bool: ...

    def coordinate_browser_fallback(
        self,
        url: str,
        failed_direct: PageResult,
        direct_fetch: Callable[[], str | PageResult | None],
        browser_fetch: Callable[[], PageResult],
        validator: Callable[[str], bool],
        timeout_ms: int,
    ) -> PageResult: ...
