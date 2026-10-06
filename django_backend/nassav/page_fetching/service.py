"""Validate direct and browser pages with the same site supplied predicate."""

import re
from collections.abc import Callable
from dataclasses import replace
from time import monotonic
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
    def __init__(
        self,
        browser: BrowserPageClient | None,
        timeout_ms: int = 60000,
        *,
        session_reuse_enabled: bool = True,
    ):
        self.browser = browser
        self.timeout_ms = timeout_ms
        self.session_reuse_enabled = session_reuse_enabled
        self.browser_unavailable = False

    def reset_lookup(self) -> None:
        self.browser_unavailable = False

    def for_lookup(self) -> "PageFetchService":
        """Give each lookup its own transient browser failure state."""
        return PageFetchService(
            self.browser,
            self.timeout_ms,
            session_reuse_enabled=self.session_reuse_enabled,
        )

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
        path_kind: str = "page",
    ) -> PageResult:
        request_id = request_id or uuid4().hex[:12]
        if not self.session_reuse_enabled:
            session_handler = None
        started = monotonic()
        direct_ms = 0
        browser_ms = 0
        browser_calls = 0

        def report(result: PageResult) -> PageResult:
            logger.info(
                "page_fetch source={} path={} request_id={} candidate={} provider={} "
                "status={} failure={} browser_calls={} version={} lock_wait_ms={} "
                "direct_ms={} byparr_ms={} total_ms={}",
                source,
                path_kind,
                request_id,
                candidate_index,
                result.provider,
                result.target_status,
                result.failure.value if result.failure else "none",
                browser_calls,
                result.session_version or "none",
                result.lock_wait_ms,
                direct_ms,
                browser_ms,
                round((monotonic() - started) * 1000),
            )
            return result

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
                browser_started = monotonic()
                result = self.browser.fetch(url, timeout_ms=self.timeout_ms)
                browser_ms += round((monotonic() - browser_started) * 1000)
                browser_calls += 1
                if result.failure == FetchFailure.CONNECTION:
                    self.browser_unavailable = True
            else:
                direct_started = monotonic()
                direct_result = direct_fetch()
                direct_ms += round((monotonic() - direct_started) * 1000)
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
            result = self.validate_result(url, result, validator)
            if not result.ok:
                logger.info(
                    "page_fetch_attempt source={} path={} request_id={} candidate={} "
                    "provider={} status={} failure={} elapsed_ms={}",
                    source,
                    path_kind,
                    request_id,
                    candidate_index,
                    result.provider,
                    result.target_status,
                    result.failure.value if result.failure else "none",
                    result.elapsed_ms,
                )
            if (
                path == "direct"
                and strategy == "direct_first"
                and session_handler is not None
                and self.browser is not None
                and (
                    result.target_status == 403
                    or result.failure == FetchFailure.CHALLENGE
                )
            ):
                browser = self.browser
                assert browser is not None
                coordinated = session_handler.coordinate_browser_fallback(
                    url,
                    result,
                    direct_fetch,
                    lambda: browser.fetch(url, timeout_ms=self.timeout_ms),
                    validator,
                    self.timeout_ms,
                )
                if (
                    coordinated.failure == FetchFailure.CONNECTION
                    and coordinated.provider != "direct"
                ):
                    self.browser_unavailable = True
                if coordinated.provider != "direct":
                    browser_calls += 1
                    browser_ms += coordinated.elapsed_ms
                else:
                    direct_ms += coordinated.elapsed_ms
                try:
                    version = session_handler.browser_session_version()
                    coordinated = replace(coordinated, session_version=version)
                except Exception:
                    pass
                return report(coordinated)
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
                        result = replace(
                            result,
                            session_version=session_handler.browser_session_version(),
                        )
                    except Exception as error:
                        logger.warning(
                            "Browser session not saved: source={} error={}",
                            source,
                            type(error).__name__,
                        )
                return report(result)
            if path == "direct" and result.target_status == 404:
                allow_session_save = False
            last = result
        return report(last)

    @classmethod
    def validate_result(
        cls, url: str, result: PageResult, validator: Callable[[str], bool]
    ) -> PageResult:
        if result.failure is not None:
            return result
        if not cls.same_site(url, result.final_url):
            return replace(result, failure=FetchFailure.PAGE_MISMATCH)
        if cls.is_challenge(result.html):
            return replace(result, failure=FetchFailure.CHALLENGE)
        if not validator(result.html):
            return replace(result, failure=FetchFailure.PAGE_MISMATCH)
        return result

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
            r"<script\b[^>]*>.*?</script>", "", html, flags=re.IGNORECASE | re.DOTALL
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
