import os
from threading import local
from time import monotonic
from typing import Optional, Protocol

from curl_cffi import requests
from curl_cffi.requests.exceptions import HTTPError
from loguru import logger
from nassav.constants import HEADERS, IMPERSONATE
from nassav.page_fetching import FetchFailure, PageResult
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

    def set_cookie_auto(self, force_refresh: bool = False) -> bool:
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

            # 如果不强制刷新，先尝试从数据库加载
            if not force_refresh:
                record = source_cookie_repository.get_cookie_record(source_name)
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

                    record = source_cookie_repository.set_cookie(
                        source_name, cookie_str
                    )
                    logger.info(f"{source_name}: Cookie已保存到数据库")
                    self.set_session(record)
                    return True
        except Exception as e:
            logger.warning(f"{self.get_source_name()}: 自动获取cookie失败: {str(e)}")
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

    def fetch_page(self, url: str, referer: str = "") -> PageResult:
        """Return direct HTML together with the actual redirected URL."""
        self.last_final_url = None
        started = monotonic()
        session = self._session_snapshot
        current_cookie = str(self.cookie or "")
        if session is None or session.cookie != current_cookie:
            session = SourceCookieRecord(self.get_source_name().lower(), current_cookie)
        if not session.usable_on_route(proxy_route_profile(self.proxy)):
            session = SourceCookieRecord(self.get_source_name().lower(), "")
        self._request_state.page_session = session
        try:
            html = self.fetch_html(url, referer=referer)
        finally:
            self._request_state.page_session = None
        return PageResult(
            html=html or "",
            elapsed_ms=round((monotonic() - started) * 1000),
            final_url=self.last_final_url or url,
            provider="direct",
            failure=None if html else FetchFailure.EMPTY,
        )

    def fetch_html(self, url: str, referer: str = "") -> Optional[str]:
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
                timeout=self.timeout,
                impersonate=IMPERSONATE,
            )
            response.raise_for_status()
            self.last_final_url = str(response.url)

            # 成功时清除上次的错误码
            self.last_error_code = None
            return response.text
        except Exception as e:
            # 尝试从异常或 response 对象获取状态码
            code = None
            try:
                # curl_cffi 的 HTTPError 可能包含 response 属性
                if isinstance(e, HTTPError) and e.response is not None:
                    code = getattr(e.response, "status_code", None)
            except Exception:
                code = None

            try:
                # 如果 response 在本地作用域可用，优先使用
                if "response" in locals() and response is not None:
                    code = getattr(response, "status_code", code)
            except Exception:
                pass

            # 异常文本可能包含请求头或代理凭据，只记录类型及状态。
            self.last_error_code = code if code is not None else type(e).__name__
            logger.error(
                f"请求失败: {type(e).__name__} (status={self.last_error_code})"
            )
            return None

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
