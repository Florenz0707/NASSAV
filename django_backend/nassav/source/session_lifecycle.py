"""Own session persistence and refresh fencing; sources own page fetching/parsing."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from time import monotonic
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from curl_cffi import requests
from curl_cffi.requests.exceptions import HTTPError
from loguru import logger
from nassav.constants import HEADERS, IMPERSONATE
from nassav.page_fetching import FetchFailure, PageFetchService, PageResult
from nassav.page_fetching.coordination import (
    SessionRefreshCoordinator,
    refresh_key,
    session_refresh_coordinator,
)
from nassav.page_fetching.session import candidate_for_page
from nassav.page_fetching.contracts import BrowserSessionHandler
from nassav.source.CookieRepository import (
    CookieRepository,
    SourceCookieRecord,
    proxy_route_profile,
    source_cookie_repository,
)

if TYPE_CHECKING:
    from .SourceBase import SourceBase


class SourceSessionLifecycle(BrowserSessionHandler):
    def __init__(
        self,
        source: SourceBase,
        repository: CookieRepository | None = None,
        coordinator: SessionRefreshCoordinator | None = None,
    ):
        self.source = source
        self.repository = (
            repository if repository is not None else source_cookie_repository
        )
        self.coordinator = (
            coordinator if coordinator is not None else session_refresh_coordinator
        )

    def set_cookie_auto(
        self,
        force_refresh: bool = False,
        *,
        write_guard: Callable[[], bool] | None = None,
    ) -> bool:
        """
        自动获取cookie并存储到数据库

        Args:
            force_refresh: 是否强制刷新cookie，即使数据库中已存在

        Returns:
            bool: 是否成功获取并设置cookie
        """
        try:
            from time import sleep

            source_name = self.source.get_source_name()

            # Capture the version before network work so a late result cannot
            # replace a manual update or another automatic refresh.
            record = self.repository.get_cookie_record(source_name)
            expected_version = record.updated_at if record is not None else None
            if not force_refresh:
                if record is not None and record.cookie:
                    self.source.set_session(record)
                    logger.info(f"{source_name}: 从数据库加载cookie")
                    return True
                logger.info(f"{source_name}: 数据库中无cookie，开始自动获取")

            home_url = self.source.get_home_url()
            headers = HEADERS.copy()
            for i in range(self.source.cookie_retry_times):
                session = requests.Session()
                logger.info(
                    f"{source_name}: 正在访问 {home_url} 获取cookie... 重试次数：{i + 1}"
                )
                response = session.get(
                    home_url,
                    proxies=self.source.proxies,  # type: ignore
                    headers=headers,
                    timeout=self.source.timeout,
                    impersonate=IMPERSONATE,
                )
                try:
                    response.raise_for_status()
                except HTTPError:
                    logger.info(f"{source_name}: 获取失败，进行重试...")
                    sleep(0.5)
                    continue

                # 获取cookie字符串
                cookies = session.cookies.get_dict()
                if not cookies:
                    logger.info(f"{source_name}: 获取失败，进行重试...")
                    sleep(0.5)
                else:
                    cookie_str = "; ".join([f"{k}={v}" for k, v in cookies.items()])
                    logger.info(
                        f"{source_name}: 成功获取cookie: {list(cookies.keys())}"
                    )

                    saved = self.repository.set_automatic_cookie_if_version(
                        source_name,
                        expected_updated_at=expected_version,
                        cookie=cookie_str,
                        write_guard=write_guard,
                    )
                    if saved is None:
                        return False
                    logger.info(f"{source_name}: Cookie已保存到数据库")
                    self.source.set_session(saved)
                    return True
        except Exception as e:
            logger.warning(
                f"{self.source.get_source_name()}: 自动获取cookie失败: {type(e).__name__}"
            )
            return False
        logger.warning(f"{source_name}：达到最大重试次数，cookie获取失败。")
        return False

    def load_cookie_from_db(self) -> bool:
        """
        从数据库加载cookie

        Returns:
            bool: 是否成功加载
        """
        try:
            source_name = self.source.get_source_name()
            record = self.repository.get_cookie_record(source_name)
            self.source.set_session(record)
            logger.info(f"{source_name}: 从数据库加载cookie成功")
            return bool(record and record.cookie)
        except Exception as e:
            logger.warning(
                f"{self.source.get_source_name()}: 从数据库加载cookie失败: {str(e)}"
            )
            return False

    def browser_session_version(self) -> str | None:
        """Capture the DB version immediately before a browser fetch."""
        record = self.repository.get_cookie_record(self.source.get_source_name())
        return record.updated_at if record is not None else None

    def accept_browser_session(
        self,
        url: str,
        result: PageResult,
        validator: Callable[[str], bool],
        expected_version: str | None,
        *,
        write_guard: Callable[[], bool] | None = None,
        refresh_key_value: str | None = None,
    ) -> bool:
        """Probe an already validated Byparr page before persisting its session."""
        if result.provider != "byparr" or not self.source.proxy:
            return False
        profile = proxy_route_profile(self.source.proxy)
        if profile is None:
            return False
        candidate = candidate_for_page(url, result)
        if candidate is None:
            return False
        previous = self.repository.get_cookie_record(self.source.get_source_name())
        if previous is not None and previous.updated_at != expected_version:
            return False
        if previous is None and expected_version is not None:
            return False
        if (
            previous is not None
            and previous.cookie == candidate.cookie
            and previous.user_agent == candidate.user_agent
            and previous.expires_at == candidate.expires_at
            and previous.egress_profile == profile
            and previous.usable_on_route(profile)
        ):
            return True
        key = refresh_key_value or refresh_key(
            self.source.get_source_name(), url, profile
        )
        try:
            if self.coordinator.store.recently_unusable(key):
                return False
        except Exception:
            # Redis is optional for browser_first; CAS still protects the row.
            if write_guard is not None:
                return False
        proposed = SourceCookieRecord(
            self.source.get_source_name().lower(),
            candidate.cookie,
            user_agent=candidate.user_agent,
            expires_at=candidate.expires_at,
            egress_profile=profile,
        )
        probe = self.source.fetch_page(
            url, session_override=proposed, timeout_seconds=3
        )
        if (
            probe.target_status != 200
            or probe.elapsed_ms > 3000
            or not probe.ok
            or not PageFetchService.same_site(url, probe.final_url)
            or PageFetchService.is_challenge(probe.html)
            or not validator(probe.html)
        ):
            try:
                self.coordinator.store.mark_unusable(key)
            except Exception:
                pass
            return False
        if write_guard is not None and not write_guard():
            return False
        saved = self.repository.set_session_if_version(
            self.source.get_source_name(),
            expected_updated_at=expected_version,
            cookie=candidate.cookie,
            user_agent=candidate.user_agent,
            expires_at=candidate.expires_at,
            egress_profile=profile,
            write_guard=write_guard,
        )
        if saved is None:
            return False
        try:
            self.coordinator.store.clear_unusable(key)
        except Exception:
            pass
        latest = self.repository.get_cookie_record(self.source.get_source_name())
        if latest == saved:
            self.source.set_session(saved)
        return True

    def coordinate_browser_fallback(
        self,
        url: str,
        failed_direct: PageResult,
        direct_fetch: Callable[[], str | PageResult | None],
        browser_fetch: Callable[[], PageResult],
        validator: Callable[[str], bool],
        timeout_ms: int,
    ) -> PageResult:
        """Single-flight a reusable session, not the page fetched by Byparr."""
        wait_started = monotonic()

        def finished(result: PageResult) -> PageResult:
            return replace(result, lock_wait_ms=lock_wait_ms)

        lock_wait_ms = 0

        def browser_page() -> PageResult:
            return PageFetchService.validate_result(url, browser_fetch(), validator)

        if not self.source.proxy:
            return finished(browser_page())
        profile = proxy_route_profile(self.source.proxy)
        if profile is None:
            return finished(browser_page())
        key = refresh_key(self.source.get_source_name(), url, profile)
        baseline = failed_direct.session_version
        coordinator = self.coordinator
        lease, busy_owner = coordinator.acquire(key, timeout_ms)

        def retry_with(record: SourceCookieRecord | None) -> PageResult | None:
            if (
                record is None
                or record.updated_at == baseline
                or not record.cookie
                or not record.user_agent
                or record.egress_profile != profile
                or not record.usable_on_route(profile)
            ):
                return None
            self.source.set_session(record)
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
            return PageFetchService.validate_result(url, result, validator)

        lock_wait_ms = round((monotonic() - wait_started) * 1000)
        if lease is None:
            if busy_owner:
                record = coordinator.wait_for_session(
                    key,
                    busy_owner,
                    baseline,
                    profile,
                    lambda: self.repository.get_cookie_record(
                        self.source.get_source_name()
                    ),
                    timeout_ms,
                )
                lock_wait_ms = round((monotonic() - wait_started) * 1000)
                retry = retry_with(record)
                if retry is not None and retry.ok:
                    return finished(retry)
            # Redis outage, expired owner, or unsuccessful refresh: this page
            # may still use Byparr, but it may not write a shared session.
            return finished(browser_page())

        outcome = "unusable"
        try:
            current = self.repository.get_cookie_record(self.source.get_source_name())
            retry = retry_with(current)
            if retry is not None and retry.ok:
                outcome = "reused"
                return finished(retry)
            expected = current.updated_at if current is not None else None
            result = browser_page()
            if result.ok and lease.owned():
                if self.accept_browser_session(
                    url,
                    result,
                    validator,
                    expected,
                    write_guard=lease.owned,
                    refresh_key_value=key,
                ):
                    outcome = "reused"
            return finished(result)
        finally:
            lease.close(outcome)

    def accept_legacy_browser_cookies(
        self,
        url: str,
        result: PageResult,
        expected_version: str | None,
        *,
        write_guard: Callable[[], bool] | None = None,
    ) -> bool:
        """Commit source-validated legacy cookies without adding reuse metadata."""
        cookies = []
        target_host = urlparse(url).hostname or ""
        for item in result.cookies:
            name, value = item.get("name"), item.get("value")
            domain = str(item.get("domain") or target_host).lstrip(".").lower()
            if (
                name
                and value
                and (target_host == domain or target_host.endswith("." + domain))
            ):
                cookies.append(f"{name}={value}")
        if not cookies:
            return False
        cookie_str = "; ".join(cookies)
        saved = self.repository.set_automatic_cookie_if_version(
            self.source.get_source_name(),
            expected_updated_at=expected_version,
            cookie=cookie_str,
            write_guard=write_guard,
        )
        if saved is None:
            return False
        self.source.set_session(saved)
        return True
