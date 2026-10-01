import os
from dataclasses import replace
from threading import local
from time import monotonic
from collections.abc import Callable
from typing import Optional, Protocol

from curl_cffi import requests
from curl_cffi.requests.exceptions import ConnectionError as CurlConnectionError
from curl_cffi.requests.exceptions import HTTPError, Timeout
from loguru import logger
from nassav.constants import HEADERS, IMPERSONATE
from nassav.page_fetching import FetchFailure, PageFetchService, PageResult
from nassav.page_fetching.coordination import (
    refresh_key,
    session_refresh_coordinator,
)
from nassav.page_fetching.session import candidate_for_page
from nassav.scraper.AVDownloadInfo import AVDownloadInfo
from nassav.source.CookieRepository import (
    SourceCookieRecord,
    proxy_route_profile,
    source_cookie_repository,
)


class ISource(Protocol):
    """Source 接口协议

    定义所有 Source 实现必须提供的方法。
    使用 Protocol 提供更好的类型检查和 IDE 支持。
    """

    def get_source_name(self) -> str:
        """获取源名称"""
        ...

    def get_html(self, avid: str) -> Optional[str]:
        """根据 AVID 获取页面 HTML"""
        ...

    def parse_html(self, html: str) -> Optional[AVDownloadInfo]:
        """解析 HTML 提取下载信息"""
        ...

    def get_cover_url(self, html: str) -> str:
        """从 HTML 中提取封面 URL"""
        ...

    def set_domain(self, domain: str) -> None:
        """设置域名"""
        ...

    def set_cookie(self, cookie: str) -> None:
        """设置 Cookie"""
        ...


class SourceBase:
    """下载源基类

    Source 的职责：
    1. 提供 M3U8 视频流地址
    2. 提供 AVID 和标题
    3. 提供封面图片 URL

    不负责：
    - 详细元数据（发行日期、时长、演员等）由 Scraper（JavBus）提供
    """

    def __init__(self, proxy: Optional[str] = None, timeout: int = 15):
        self.proxy = proxy
        self.proxies = {"http": proxy, "https": proxy} if proxy else None
        self.cookie = None
        self._session_snapshot: SourceCookieRecord | None = None
        self.cookie_retry_times = 5
        self.timeout = timeout
        self.domain = ""
        # 最近一次 fetch_html 请求的响应状态码（成功时为 None）
        self.last_error_code = None
        self._request_state = local()
        self.last_final_url = None

    @property
    def last_final_url(self) -> str | None:
        return getattr(self._request_state, "final_url", None)

    @last_final_url.setter
    def last_final_url(self, value: str | None) -> None:
        self._request_state.final_url = value

    def search_listing(
        self,
        kind: str,
        term: str,
        *,
        page: int = 1,
        ordering: str = "-views",
        force_refresh: bool = False,
    ) -> list[dict]:
        """Fetch source-native listing items; unsupported sources reject explicitly."""
        raise NotImplementedError("This source does not support listing search")

    def set_domain(self, domain: str):
        self.domain = domain

    def set_cookie(self, cookie: str):
        self.cookie = cookie
        self._session_snapshot = SourceCookieRecord(
            self.get_source_name().lower(), cookie
        )

    def set_session(self, session: SourceCookieRecord | None) -> None:
        """Swap a complete snapshot; legacy download calls still see cookie."""
        self.cookie = session.cookie if session is not None else ""
        self._session_snapshot = session

    def get_source_name(self) -> str:
        raise NotImplementedError

    def _get_home_url(self) -> str:
        """获取首页URL，用于cookie获取。子类可以重写此方法"""
        if not self.domain:
            raise ValueError(f"{self.get_source_name()} 未设置domain")
        return f"https://{self.domain}/"

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

            source_name = self.get_source_name()

            # Capture the version before network work so a late result cannot
            # replace a manual update or another automatic refresh.
            record = source_cookie_repository.get_cookie_record(source_name)
            expected_version = record.updated_at if record is not None else None
            if not force_refresh:
                if record is not None and record.cookie:
                    self.set_session(record)
                    logger.info(f"{source_name}: 从数据库加载cookie")
                    return True
                logger.info(f"{source_name}: 数据库中无cookie，开始自动获取")

            home_url = self._get_home_url()
            headers = HEADERS.copy()
            for i in range(self.cookie_retry_times):
                session = requests.Session()
                logger.info(
                    f"{source_name}: 正在访问 {home_url} 获取cookie... 重试次数：{i + 1}"
                )
                response = session.get(
                    home_url,
                    proxies=self.proxies,  # type: ignore
                    headers=headers,
                    timeout=self.timeout,
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

                    saved = source_cookie_repository.set_automatic_cookie_if_version(
                        source_name,
                        expected_updated_at=expected_version,
                        cookie=cookie_str,
                        write_guard=write_guard,
                    )
                    if saved is None:
                        return False
                    logger.info(f"{source_name}: Cookie已保存到数据库")
                    self.set_session(saved)
                    return True
        except Exception as e:
            logger.warning(
                f"{self.get_source_name()}: 自动获取cookie失败: {type(e).__name__}"
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
            source_name = self.get_source_name()
            record = source_cookie_repository.get_cookie_record(source_name)
            self.set_session(record)
            logger.info(f"{source_name}: 从数据库加载cookie成功")
            return bool(record and record.cookie)
        except Exception as e:
            logger.warning(
                f"{self.get_source_name()}: 从数据库加载cookie失败: {str(e)}"
            )
            return False

    def get_html(self, avid: str) -> Optional[str]:
        raise NotImplementedError

    def parse_html(self, html: str) -> Optional[AVDownloadInfo]:
        raise NotImplementedError

    def get_cover_url(self, html: str) -> str:
        raise NotImplementedError

    def fetch_page(
        self,
        url: str,
        referer: str = "",
        *,
        session_override: SourceCookieRecord | None = None,
        timeout_seconds: float | None = None,
    ) -> PageResult:
        """Make one direct request using one immutable Cookie and UA snapshot."""
        self.last_final_url = None
        self._request_state.direct_status = None
        self._request_state.direct_failure = None
        started = monotonic()
        session = session_override or self._session_snapshot
        current_cookie = str(self.cookie or "")
        if session_override is None and (
            session is None or session.cookie != current_cookie
        ):
            session = SourceCookieRecord(self.get_source_name().lower(), current_cookie)
        if (
            session_override is None
            and not getattr(
                getattr(self, "page_fetcher", None), "session_reuse_enabled", True
            )
            and session is not None
        ):
            session = SourceCookieRecord(self.get_source_name().lower(), session.cookie)
        if session is None or not session.usable_on_route(
            proxy_route_profile(self.proxy)
        ):
            session = SourceCookieRecord(self.get_source_name().lower(), "")
        self._request_state.page_session = session
        self._request_state.timeout_override = timeout_seconds
        try:
            html = self.fetch_html(url, referer=referer)
        finally:
            self._request_state.page_session = None
            self._request_state.timeout_override = None
        return PageResult(
            html=html or "",
            elapsed_ms=round((monotonic() - started) * 1000),
            final_url=self.last_final_url or url,
            provider="direct",
            target_status=self._request_state.direct_status,
            session_version=session.updated_at,
            failure=self._request_state.direct_failure
            or (None if html else FetchFailure.EMPTY),
        )

    def fetch_html(self, url: str, referer: str = "") -> Optional[str]:
        self._request_state.direct_status = None
        self._request_state.direct_failure = None
        response = None
        try:
            headers = HEADERS.copy()
            if referer:
                headers["Referer"] = referer
            session = getattr(self._request_state, "page_session", None)
            if session is not None:
                if session.cookie:
                    headers["Cookie"] = session.cookie
                if session.user_agent:
                    headers["User-Agent"] = session.user_agent
            elif self.cookie:
                headers["Cookie"] = self.cookie

            response = requests.get(
                url,
                proxies=self.proxies,  # type: ignore
                headers=headers,
                timeout=getattr(self._request_state, "timeout_override", None)
                or self.timeout,
                impersonate=IMPERSONATE,
            )
            self._request_state.direct_status = getattr(response, "status_code", 200)
            self.last_final_url = str(response.url)
            response.raise_for_status()
            self.last_error_code = None
            return response.text
        except Exception as error:
            code = getattr(response, "status_code", None)
            if code is None and isinstance(error, HTTPError):
                code = getattr(error.response, "status_code", None)
            self._request_state.direct_status = code
            if isinstance(error, Timeout):
                failure = FetchFailure.TIMEOUT
            elif isinstance(error, CurlConnectionError):
                failure = FetchFailure.CONNECTION
            elif code is not None:
                failure = FetchFailure.TARGET_HTTP
            else:
                failure = FetchFailure.CONNECTION
            self._request_state.direct_failure = failure
            # Exception text may contain Cookie headers or proxy credentials.
            self.last_error_code = code if code is not None else type(error).__name__
            logger.error(
                f"请求失败: {type(error).__name__} (status={self.last_error_code})"
            )
            return None

    def browser_session_version(self) -> str | None:
        """Capture the DB version immediately before a browser fetch."""
        record = source_cookie_repository.get_cookie_record(self.get_source_name())
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
        if result.provider != "byparr" or not self.proxy:
            return False
        profile = proxy_route_profile(self.proxy)
        if profile is None:
            return False
        candidate = candidate_for_page(url, result)
        if candidate is None:
            return False
        previous = source_cookie_repository.get_cookie_record(self.get_source_name())
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
        key = refresh_key_value or refresh_key(self.get_source_name(), url, profile)
        try:
            if session_refresh_coordinator.store.recently_unusable(key):
                return False
        except Exception:
            # Redis is optional for browser_first; CAS still protects the row.
            if write_guard is not None:
                return False
        proposed = SourceCookieRecord(
            self.get_source_name().lower(),
            candidate.cookie,
            user_agent=candidate.user_agent,
            expires_at=candidate.expires_at,
            egress_profile=profile,
        )
        probe = self.fetch_page(url, session_override=proposed, timeout_seconds=3)
        if (
            probe.target_status != 200
            or probe.elapsed_ms > 3000
            or not probe.ok
            or not PageFetchService.same_site(url, probe.final_url)
            or PageFetchService.is_challenge(probe.html)
            or not validator(probe.html)
        ):
            try:
                session_refresh_coordinator.store.mark_unusable(key)
            except Exception:
                pass
            return False
        if write_guard is not None and not write_guard():
            return False
        saved = source_cookie_repository.set_session_if_version(
            self.get_source_name(),
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
            session_refresh_coordinator.store.clear_unusable(key)
        except Exception:
            pass
        latest = source_cookie_repository.get_cookie_record(self.get_source_name())
        if latest == saved:
            self.set_session(saved)
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

        if not self.proxy:
            return finished(browser_page())
        profile = proxy_route_profile(self.proxy)
        if profile is None:
            return finished(browser_page())
        key = refresh_key(self.get_source_name(), url, profile)
        baseline = failed_direct.session_version
        coordinator = session_refresh_coordinator
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
            self.set_session(record)
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
                    lambda: source_cookie_repository.get_cookie_record(
                        self.get_source_name()
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
            current = source_cookie_repository.get_cookie_record(self.get_source_name())
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

    def download_file(self, url: str, save_path: str, referer: str = "") -> bool:
        """下载文件到指定路径"""
        try:
            headers = HEADERS.copy()
            if referer:
                headers["Referer"] = referer
            if self.cookie:
                headers["Cookie"] = self.cookie

            response = requests.get(
                url,
                stream=True,
                impersonate=IMPERSONATE,
                proxies=self.proxies,  # type: ignore
                headers=headers,
                timeout=self.timeout,
                allow_redirects=True,
            )
            response.raise_for_status()

            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            with open(save_path, "wb") as f:
                # curl_cffi 不支持 chunk_size 参数,直接使用 iter_content()
                for chunk in response.iter_content():
                    if chunk:
                        f.write(chunk)

            return True
        except Exception as e:
            logger.error(f"下载失败: {e}")
            return False
