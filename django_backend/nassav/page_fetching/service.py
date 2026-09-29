"""Validate direct and browser pages with the same site supplied predicate."""

from collections.abc import Callable
import re
from dataclasses import replace
from urllib.parse import urlparse
from uuid import uuid4

from loguru import logger

from .contracts import (
    BrowserPageClient,
    BrowserSessionHandler,
    FetchFailure,
    PageResult,
)


class PageFetchService:
    def __init__(self, browser: BrowserPageClient | None, timeout_ms: int = 60000):
        self.browser = browser
        self.timeout_ms = timeout_ms
        self.browser_unavailable = False

    def reset_lookup(self) -> None:
        self.browser_unavailable = False

    def for_lookup(self) -> "PageFetchService":
        """Give each lookup its own transient browser failure state."""
        return PageFetchService(self.browser, self.timeout_ms)

    def fetch(
        self,
        url: str,
        *,
        direct_fetch: Callable[[], str | PageResult | None],
        validator: Callable[[str], bool],
        strategy: str,
        source: str = "",
        candidate_index: int = 1,
        request_id: str = "",
        session_handler: BrowserSessionHandler | None = None,
    ) -> PageResult:
        request_id = request_id or uuid4().hex[:12]
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
        allow_session_save = True
        for path in paths:
            if path == "browser":
                if self.browser is None or self.browser_unavailable:
                    continue
                can_save_session = False
                expected_version = None
                if session_handler is not None:
                    try:
                        expected_version = session_handler.browser_session_version()
                        can_save_session = True
                    except Exception as error:
                        logger.warning(
                            "Browser session version unavailable: source={} error={}",
                            source,
                            type(error).__name__,
                        )
                result = self.browser.fetch(url, timeout_ms=self.timeout_ms)
                if result.failure == FetchFailure.CONNECTION:
                    self.browser_unavailable = True
            else:
                direct_result = direct_fetch()
                if isinstance(direct_result, PageResult):
                    result = direct_result
                else:
                    result = PageResult(
                        html=direct_result or "",
                        final_url=url,
                        provider="direct",
                        failure=None if direct_result else FetchFailure.EMPTY,
                    )
            if (
                path == "direct"
                and result.failure is None
                and result.target_status is not None
                and result.target_status != 200
            ):
                result = replace(result, failure=FetchFailure.TARGET_HTTP)
            if result.failure is None:
                if not self.same_site(url, result.final_url):
                    result = replace(result, failure=FetchFailure.PAGE_MISMATCH)
                elif self.is_challenge(result.html):
                    result = replace(result, failure=FetchFailure.CHALLENGE)
                elif not validator(result.html):
                    result = replace(result, failure=FetchFailure.PAGE_MISMATCH)
            if result.ok:
                if (
                    path == "browser"
                    and can_save_session
                    and allow_session_save
                    and session_handler is not None
                ):
                    try:
                        session_handler.accept_browser_session(
                            url, result, validator, expected_version
                        )
                    except Exception as error:
                        logger.warning(
                            "Browser session not saved: source={} error={}",
                            source,
                            type(error).__name__,
                        )
                logger.info(
                    "Page fetch success: source={} provider={} request_id={} candidate={} elapsed_ms={}",
                    source,
                    result.provider,
                    request_id,
                    candidate_index,
                    result.elapsed_ms,
                )
                return result
            if path == "direct" and result.target_status == 404:
                allow_session_save = False
            last = result
            logger.info(
                "Page fetch failed: source={} provider={} request_id={} candidate={} elapsed_ms={} failure={}",
                source,
                result.provider,
                request_id,
                candidate_index,
                result.elapsed_ms,
                result.failure,
            )
        return last

    @staticmethod
    def same_site(requested: str, final: str) -> bool:
        requested_host = urlparse(requested).hostname
        final_host = urlparse(final).hostname
        return bool(requested_host and requested_host == final_host)

    @staticmethod
    def is_challenge(html: str) -> bool:
        # Valid MissAV pages can embed a challenge-platform script. The
        # marker only indicates a challenge when it appears in visible HTML.
        lowered = re.sub(
            r"<script\b[^>]*>.*?</script>", "", html, flags=re.I | re.S
        ).lower()
        return any(
            marker in lowered
            for marker in (
                "cf-challenge",
                "challenge-platform",
                "checking your browser",
                "just a moment...",
            )
        )
