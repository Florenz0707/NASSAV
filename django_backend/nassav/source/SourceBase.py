from __future__ import annotations

import os
from abc import abstractmethod
from collections.abc import Callable
from threading import local
from time import monotonic
from typing import TYPE_CHECKING

from curl_cffi import requests
from curl_cffi.requests.exceptions import ConnectionError as CurlConnectionError
from curl_cffi.requests.exceptions import HTTPError, Timeout
from loguru import logger

from nassav.constants import HEADERS, IMPERSONATE
from nassav.page_fetching import FetchFailure, PageResult
from nassav.page_fetching.contracts import BrowserSessionHandler
from nassav.page_fetching.coordination import SessionRefreshCoordinator
from nassav.resource_contracts import SourceRelations
from nassav.scraper.AVDownloadInfo import AVDownloadInfo
from nassav.source.CookieRepository import (
    CookieRepository,
    SourceCookieRecord,
    proxy_route_profile,
)
from nassav.source.session_lifecycle import SourceSessionLifecycle

if TYPE_CHECKING:
    from nassav.scoped_source_context import ScopedSourceContext


class SourceBase(BrowserSessionHandler):
    """下载源基类

    Source 的职责：
    1. 提供 M3U8 视频流地址
    2. 提供 AVID 和标题
    3. 提供封面图片 URL

    不负责：
    - 详细元数据（发行日期、时长、演员等）由 Scraper（JavBus）提供
    """

    DEFAULT_DOMAIN = ""

    def __init__(
        self,
        proxy: str | None = None,
        timeout: int = 15,
        *,
        cookie_repository: CookieRepository | None = None,
        refresh_coordinator: SessionRefreshCoordinator | None = None,
    ):
        self.proxy = proxy
        self.proxies = {"http": proxy, "https": proxy} if proxy else None
        self.cookie = None
        self._session_snapshot: SourceCookieRecord | None = None
        self.cookie_retry_times = 5
        self.timeout = timeout
        self.domain = ""
        self.task_control = None
        self.credential_context: ScopedSourceContext | None = None
        # 最近一次 fetch_html 请求的响应状态码（成功时为 None）
        self.last_error_code = None
        self._request_state = local()
        self.last_final_url = None
        self._sessions = SourceSessionLifecycle(
            self, cookie_repository, refresh_coordinator
        )

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

    def parse_relations(self, html: str) -> SourceRelations:
        """Optional source-native relation data; never performs persistence."""
        return SourceRelations()

    def get_detail_url(self, avid: str) -> str:
        return f"https://{self.domain}/{avid.lower()}"

    def fetch_provider_facts(self, avid: str, detail_url: str = ""):
        from nassav.provider_facts import parse_source_facts

        html = self.get_html(avid)
        self._check_task()
        if not html:
            raise ValueError("Source page unavailable")
        metadata, playback = parse_source_facts(self, avid, html)
        return metadata, playback, html

    def set_domain(self, domain: str):
        self.domain = domain

    def set_task_control(self, control) -> None:
        self.task_control = control

    def _fetch(self, url, **kwargs):
        protected = False
        if self.credential_context is not None:
            headers = self.credential_context.filter_headers(
                url, kwargs.get("headers", {})
            )
            kwargs["headers"] = headers
            protected = any(key.lower() == "cookie" for key in headers)
            if protected:
                kwargs["allow_redirects"] = False
        if self.task_control is not None:
            response = self.task_control.request("GET", url, **kwargs)
        else:
            response = requests.get(url, **kwargs)
        if protected and 300 <= response.status_code < 400:
            raise HTTPError("Credential redirects are not permitted")
        return response

    def _check_task(self) -> None:
        if self.task_control is not None:
            self.task_control.check()
        if self.credential_context is not None:
            self.credential_context.check()

    def bind_credential_context(self, context: ScopedSourceContext):
        self.credential_context = context

    @property
    def requires_bound_page(self):
        return self.credential_context is not None

    def bind_browser_page(self, url, result, validator):
        if self.credential_context is None:
            return result
        return self.credential_context.bind_browser_page(
            url, result, validator, self.fetch_page
        )

    def fetch_bound_browser_page(self, url, browser_fetch, validator, timeout_ms):
        if self.credential_context is None:
            return browser_fetch()
        return self.credential_context.fetch_browser_page(
            url, browser_fetch, validator, self.fetch_page, timeout_ms
        )

    def set_cookie(self, cookie: str):
        self.cookie = cookie
        self._session_snapshot = SourceCookieRecord(
            self.get_source_name().lower(), cookie
        )

    def set_session(self, session: SourceCookieRecord | None) -> None:
        """Swap a complete snapshot; legacy download calls still see cookie."""
        self.cookie = session.cookie if session is not None else ""
        self._session_snapshot = session

    @abstractmethod
    def get_source_name(self) -> str:
        raise NotImplementedError

    def get_home_url(self) -> str:
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
        if self.credential_context is not None:
            return False
        return self._sessions.set_cookie_auto(force_refresh, write_guard=write_guard)

    def load_cookie_from_db(self) -> bool:
        if self.credential_context is not None:
            record = self.credential_context.load_session()
            self.set_session(record)
            return bool(record and record.cookie)
        return self._sessions.load_cookie_from_db()

    @abstractmethod
    def get_html(self, avid: str) -> str | None:
        raise NotImplementedError

    @abstractmethod
    def parse_html(self, html: str) -> AVDownloadInfo | None:
        raise NotImplementedError

    @abstractmethod
    def get_cover_url(self, html: str) -> str | None:
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
        if self.credential_context is not None and session_override is None:
            self.set_session(self.credential_context.load_session())
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
            and self.credential_context is None
            and not getattr(
                getattr(self, "page_fetcher", None), "session_reuse_enabled", True
            )
            and session is not None
        ):
            session = SourceCookieRecord(self.get_source_name().lower(), session.cookie)
        if session is None or not session.usable_on_route(
            proxy_route_profile(self.proxy)
        ):
            if (
                self.credential_context is not None
                and session is not None
                and session.cookie
            ):
                from nassav.credential_crypto import CredentialUnavailable

                raise CredentialUnavailable("Credential route mismatch")
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

    def fetch_html(self, url: str, referer: str = "") -> str | None:
        self._check_task()
        self._request_state.direct_status = None
        self._request_state.direct_failure = None
        response = None
        try:
            headers = HEADERS.copy()
            if referer:
                headers["Referer"] = referer
            session = getattr(self._request_state, "page_session", None)
            if session is None and self.credential_context is not None:
                session = self.credential_context.load_session()
            if session is not None:
                if session.cookie:
                    headers["Cookie"] = session.cookie
                if session.user_agent:
                    headers["User-Agent"] = session.user_agent
            elif self.cookie:
                headers["Cookie"] = self.cookie

            response = self._fetch(
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
            self._check_task()
            self.last_error_code = None
            return response.text
        except Exception as error:
            self._check_task()
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
        if self.credential_context is not None:
            record = self.credential_context.load_session()
            return record.updated_at if record else None
        return self._sessions.browser_session_version()

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
        self._check_task()
        if self.credential_context is not None:
            return False  # Scoped replay already owns persistence; never dual-write.
        original_guard = write_guard

        def guarded():
            self._check_task()
            return original_guard() if original_guard else True

        return self._sessions.accept_browser_session(
            url,
            result,
            validator,
            expected_version,
            write_guard=guarded if self.task_control is not None else write_guard,
            refresh_key_value=refresh_key_value,
        )

    def coordinate_browser_fallback(
        self,
        url: str,
        failed_direct: PageResult,
        direct_fetch: Callable[[], str | PageResult | None],
        browser_fetch: Callable[[], PageResult],
        validator: Callable[[str], bool],
        timeout_ms: int,
    ) -> PageResult:
        if self.credential_context is not None:
            return self.fetch_bound_browser_page(
                url, browser_fetch, validator, timeout_ms
            )
        return self._sessions.coordinate_browser_fallback(
            url, failed_direct, direct_fetch, browser_fetch, validator, timeout_ms
        )

    def download_file(self, url: str, save_path: str, referer: str = "") -> bool:
        """下载文件到指定路径"""
        self._check_task()
        try:
            headers = HEADERS.copy()
            if referer:
                headers["Referer"] = referer
            if self.cookie:
                headers["Cookie"] = self.cookie

            response = self._fetch(
                url,
                stream=self.task_control is None,
                impersonate=IMPERSONATE,
                proxies=self.proxies,  # type: ignore
                headers=headers,
                timeout=self.timeout,
                allow_redirects=True,
            )
            response.raise_for_status()

            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            if self.task_control is not None:
                from pathlib import Path

                self.task_control.write(Path(save_path), response.content)
                return True
            with open(save_path, "wb") as f:
                # curl_cffi 不支持 chunk_size 参数,直接使用 iter_content()
                for chunk in response.iter_content():
                    if chunk:
                        f.write(chunk)

            return True
        except Exception as e:
            self._check_task()
            logger.error(f"下载失败: {e}")
            return False
