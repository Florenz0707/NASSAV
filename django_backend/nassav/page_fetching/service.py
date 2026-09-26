"""Validate direct and browser pages with the same site supplied predicate."""

from collections.abc import Callable
from urllib.parse import urlparse

from loguru import logger

from .contracts import BrowserPageClient, FetchFailure, PageResult


class PageFetchService:
    def __init__(self, browser: BrowserPageClient | None, timeout_ms: int = 60000):
        self.browser = browser
        self.timeout_ms = timeout_ms
        self.browser_unavailable = False

    def reset_lookup(self) -> None:
        self.browser_unavailable = False

    def fetch(
        self,
        url: str,
        *,
        direct_fetch: Callable[[], str | None],
        validator: Callable[[str], bool],
        strategy: str,
    ) -> PageResult:
        if strategy not in {"browser_first", "direct_first", "direct_only"}:
            raise ValueError(f"Unknown page fetch strategy: {strategy}")
        paths = (
            ("direct",)
            if strategy == "direct_only"
            else (
                ("browser", "direct")
                if strategy == "browser_first"
                else ("direct", "browser")
            )
        )
        last = PageResult(final_url=url, failure=FetchFailure.EMPTY)
        for path in paths:
            if path == "browser":
                if self.browser is None or self.browser_unavailable:
                    continue
                result = self.browser.fetch(url, timeout_ms=self.timeout_ms)
                if result.failure == FetchFailure.CONNECTION:
                    self.browser_unavailable = True
            else:
                html = direct_fetch()
                result = PageResult(
                    html=html or "",
                    final_url=url,
                    provider="direct",
                    failure=None if html else FetchFailure.EMPTY,
                )
            if result.failure is None:
                if not self.same_site(url, result.final_url):
                    result = PageResult(
                        final_url=result.final_url,
                        provider=result.provider,
                        failure=FetchFailure.PAGE_MISMATCH,
                    )
                elif self.is_challenge(result.html):
                    result = PageResult(
                        final_url=result.final_url,
                        provider=result.provider,
                        failure=FetchFailure.CHALLENGE,
                    )
                elif not validator(result.html):
                    result = PageResult(
                        final_url=result.final_url,
                        provider=result.provider,
                        failure=FetchFailure.PAGE_MISMATCH,
                    )
            if result.ok:
                return result
            last = result
            logger.info(
                "Page fetch failed: provider={} failure={} url={}",
                result.provider,
                result.failure,
                url,
            )
        return last

    @staticmethod
    def same_site(requested: str, final: str) -> bool:
        requested_host = urlparse(requested).hostname
        final_host = urlparse(final).hostname
        return bool(requested_host and requested_host == final_host)

    @staticmethod
    def is_challenge(html: str) -> bool:
        lowered = html.lower()
        return any(
            marker in lowered
            for marker in (
                "cf-challenge",
                "challenge-platform",
                "checking your browser",
                "just a moment...",
            )
        )
