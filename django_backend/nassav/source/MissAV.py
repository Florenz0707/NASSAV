import re
from collections.abc import Callable
from typing import Optional, Tuple

from curl_cffi import requests
from django.conf import settings
from loguru import logger
from nassav.constants import IMPERSONATE
from nassav.page_fetching import (
    PageFetchService,
    create_page_fetch_service,
    validate_strategy,
)
from nassav.source.CookieRepository import CookieRepository
from nassav.page_fetching.coordination import SessionRefreshCoordinator
from nassav.scraper.AVDownloadInfo import AVDownloadInfo
from nassav.source.SourceBase import SourceBase
from nassav.source.capabilities import ListingSource
from nassav.source.MissAVListings import (
    listing_url,
    parse_listing,
    valid_listing,
    verify_listing_url,
)
from nassav.source.search_contracts import SourceSearchError


class MissAV(SourceBase, ListingSource):
    """MissAV下载器"""

    def __init__(
        self,
        proxy: Optional[str] = None,
        timeout: int = 15,
        *,
        page_fetcher: PageFetchService | None = None,
        cookie_repository: CookieRepository | None = None,
        refresh_coordinator: SessionRefreshCoordinator | None = None,
        cookie_saver=None,
    ):
        super().__init__(
            proxy,
            timeout,
            cookie_repository=cookie_repository,
            refresh_coordinator=refresh_coordinator,
        )
        source_config = settings.SOURCE_CONFIG.get("missav", {})
        self.domain = source_config.get("domain", "missav.ai")
        self.browser_fetch_strategy = validate_strategy(
            source_config.get("browser_fetch_strategy", "browser_first")
        )
        self.page_fetcher = page_fetcher or create_page_fetch_service(
            settings.BROWSER_FETCH_CONFIG, proxy_url=proxy
        )
        self._cookie_saver = cookie_saver

    def get_source_name(self) -> str:
        return "MissAV"

    def search_listing(
        self,
        kind: str,
        term: str,
        *,
        page: int = 1,
        ordering: str = "-views",
        force_refresh: bool = False,
    ) -> list[dict]:
        # The external search service owns validated result caching.
        url = listing_url(self.domain, kind, term, page, ordering)
        fetcher = self.page_fetcher.for_lookup()
        result = fetcher.fetch(
            url,
            direct_fetch=lambda: self.fetch_page(
                url, referer=f"https://{self.domain}/cn/"
            ),
            validator=lambda html: valid_listing(html, self.domain),
            strategy=self.browser_fetch_strategy,
            source=self.get_source_name(),
            path_kind="search" if kind == "search" else "listing",
            session_handler=self
            if fetcher.session_reuse_enabled
            and self.proxy
            and getattr(fetcher.browser, "provider", None) == "byparr"
            else None,
        )
        if not result.ok:
            raise SourceSearchError(f"missav_listing_{result.failure}")
        verify_listing_url(url, result.final_url)
        return parse_listing(result.html, self.domain)

    def get_html(self, avid: str) -> Optional[str]:
        """Fetch candidates in their original order and validate both paths alike."""
        import time
        from uuid import uuid4

        request_id = uuid4().hex[:12]
        avid_lower = avid.lower()
        urls = [
            f"https://{self.domain}/cn/{avid_lower}",
            f"https://{self.domain}/cn/{avid_lower}-chinese-subtitle",
            f"https://{self.domain}/{avid_lower}-chinese-subtitle",
        ]
        fetcher = self.page_fetcher.for_lookup()
        for candidate_index, url in enumerate(urls, start=1):
            result = fetcher.fetch(
                url,
                direct_fetch=lambda url=url: self.fetch_page(
                    url, referer=f"https://{self.domain}/search/{avid_lower}"
                ),
                validator=lambda html: self._is_detail_page_html(html, avid),
                strategy=self.browser_fetch_strategy,
                source=self.get_source_name(),
                candidate_index=candidate_index,
                request_id=request_id,
                path_kind="detail",
                session_handler=self
                if fetcher.session_reuse_enabled
                and self.proxy
                and getattr(fetcher.browser, "provider", None) == "byparr"
                else None,
            )
            if result.ok:
                return result.html
            if candidate_index < len(urls):
                time.sleep(1)
        return None

    def _is_detail_page_html(self, html: str, avid: str) -> bool:
        if not self._extract_uuid(html):
            return False
        title = re.search(r'<meta property="og:title" content="(.*?)"', html)
        return bool(title and avid.lower() in title.group(1).lower())

    def set_cookie_auto(
        self,
        force_refresh: bool = False,
        *,
        write_guard: Callable[[], bool] | None = None,
    ) -> bool:
        """Save browser cookies only after validating the home page."""
        if not self.page_fetcher.browser:
            return super().set_cookie_auto(force_refresh, write_guard=write_guard)
        source_name = self.get_source_name()
        existing = self._sessions.repository.get_cookie_record(source_name)
        expected_version = existing.updated_at if existing is not None else None
        if not force_refresh:
            if existing is not None and existing.cookie:
                self.set_session(existing)
                return True
        home_url = f"https://{self.domain}/"
        result = self.page_fetcher.browser.fetch(
            home_url, timeout_ms=self.page_fetcher.timeout_ms
        )
        if not result.ok or not self.page_fetcher.same_site(home_url, result.final_url):
            return False
        if (
            self.page_fetcher.is_challenge(result.html)
            or "missav" not in result.html.lower()
        ):
            return False
        return self._sessions.accept_legacy_browser_cookies(
            home_url, result, expected_version, write_guard=write_guard
        )

    def parse_html(self, html: str) -> Optional[AVDownloadInfo]:
        """解析 HTML 获取核心下载信息（m3u8、avid、title）

        其他元数据（发行日期、时长、演员等）由 JavBus Scraper 提供
        """
        info = AVDownloadInfo()
        info.source = self.get_source_name()

        # 1. 提取 m3u8（必需）
        uuid = self._extract_uuid(html)
        if uuid:
            playlist_url = f"https://surrit.com/{uuid}/playlist.m3u8"
            result = self._get_highest_quality_m3u8(playlist_url)
            if result:
                m3u8_url, resolution = result
                info.m3u8 = m3u8_url
            else:
                logger.error("未找到有效视频流")
                return None
        else:
            logger.error("未找到有效 uuid")
            return None

        # 2. 提取标题和 AVID
        if not self._extract_metadata(html, info):
            return None

        return info

    def _extract_uuid(self, html: str) -> Optional[str]:
        try:
            match = re.search(r"m3u8\|([a-f0-9|]+)\|com\|surrit\|https\|video", html)
            if match:
                return "-".join(match.group(1).split("|")[::-1])
            return None
        except Exception as e:
            logger.error(f"UUID提取异常: {str(e)}")
            return None

    def _extract_metadata(self, html: str, metadata: AVDownloadInfo) -> bool:
        """提取核心元数据：AVID 和 source_title（备用标题）"""
        try:
            og_title = re.search(r'<meta property="og:title" content="(.*?)"', html)
            if og_title:
                title_content = og_title.group(1)
                # 尝试从标题中分离 AVID
                code_match = re.search(r"^([A-Z]+(?:-[A-Z]+)*-\d+)", title_content)
                if code_match:
                    metadata.avid = code_match.group(1)
                    metadata.source_title = title_content.replace(
                        metadata.avid, ""
                    ).strip()
                else:
                    metadata.source_title = title_content.strip()
            return True
        except Exception as e:
            logger.error(f"核心元数据解析异常: {str(e)}")
            return False

    def _get_highest_quality_m3u8(self, playlist_url: str) -> Optional[Tuple[str, str]]:
        try:
            response = requests.get(playlist_url, timeout=10, impersonate=IMPERSONATE)
            response.raise_for_status()
            playlist_content = response.text

            streams = []
            pattern = re.compile(
                r"#EXT-X-STREAM-INF:BANDWIDTH=(\d+),.*?RESOLUTION=(\d+x\d+).*?\n(.*)"
            )

            for match in pattern.finditer(playlist_content):
                bandwidth = int(match.group(1))
                resolution = match.group(2)
                url = match.group(3).strip()
                streams.append((bandwidth, resolution, url))

            streams.sort(reverse=True, key=lambda x: x[0])

            if streams:
                best_stream = streams[0]
                base_url = playlist_url.rsplit("/", 1)[0]
                full_url = (
                    f"{base_url}/{best_stream[2]}"
                    if not best_stream[2].startswith("http")
                    else best_stream[2]
                )
                return full_url, best_stream[1]
            return None

        except Exception as e:
            logger.error(f"获取最高质量流失败: {str(e)}")
            return None

    def get_cover_url(self, html: str) -> Optional[str]:
        """从HTML中提取封面URL"""
        try:
            # MissAV的封面通常在og:image标签中
            match = re.search(r'<meta property="og:image" content="([^"]+)"', html)
            if match:
                return match.group(1)
            return None
        except Exception as e:
            logger.error(f"封面URL提取失败: {e}")
            return None
