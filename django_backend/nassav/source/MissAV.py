import re
from typing import Optional, Tuple

from curl_cffi import requests
from django.conf import settings
from loguru import logger
from nassav.constants import HEADERS, IMPERSONATE
from nassav.flaresolverr_client import FlareSolverrClient
from nassav.scraper.AVDownloadInfo import AVDownloadInfo
from nassav.source.SourceBase import SourceBase


class MissAV(SourceBase):
    """MissAV下载器"""

    def __init__(self, proxy: Optional[str] = None, timeout: int = 15):
        super().__init__(proxy, timeout)
        source_config = settings.SOURCE_CONFIG.get("missav", {})
        self.domain = source_config.get("domain", "missav.ai")

        # FlareSolverr：当 curl_cffi 被 Cloudflare 拦截时使用
        if settings.FLARESOLVERR_ENABLED:
            self._flaresolverr = FlareSolverrClient(
                base_url=settings.FLARESOLVERR_URL,
                timeout_ms=settings.FLARESOLVERR_TIMEOUT,
            )
        else:
            self._flaresolverr = None

    def get_source_name(self) -> str:
        return "MissAV"

    def get_html(self, avid: str) -> Optional[str]:
        """根据avid获取HTML

        若 FlareSolverr 已启用，优先通过 FlareSolverr 请求（绕过 Cloudflare）；
        FlareSolverr 失败时回退到 curl_cffi。未启用则直接使用 curl_cffi。
        """
        import time

        avid_lower = avid.lower()
        urls = [
            f"https://{self.domain}/cn/{avid_lower}-chinese-subtitle",
            f"https://{self.domain}/{avid_lower}-chinese-subtitle",
            f"https://{self.domain}/cn/{avid_lower}",
        ]

        for url in urls:
            # 1. FlareSolverr 优先（已启用时）
            if self._flaresolverr:
                logger.info(f"MissAV: 通过 FlareSolverr 请求: {url}")
                solution = self._flaresolverr.get(url)
                if solution and solution.get("status") == 200:
                    content = solution.get("response", "")
                    # 有效视频页面必含 surrit（CDN 域名），404 页面不含
                    if content and "surrit" in content:
                        return content
                    logger.info(f"MissAV: FlareSolverr 返回页面无视频内容（可能是404），跳过: {url}")
                logger.info(f"MissAV: FlareSolverr 失败或页面无效，回退到 curl_cffi: {url}")

            # 2. curl_cffi 兜底
            content = self.fetch_html(
                url, referer=f"https://{self.domain}/search/{avid_lower}"
            )
            time.sleep(1)
            if content:
                return content

        return None

    def set_cookie_auto(self, force_refresh: bool = False) -> bool:
        """自动获取 cookie

        若 FlareSolverr 已启用，优先通过 FlareSolverr 获取 cf_clearance；
        否则回退到基类的 curl_cffi 实现。
        """
        if not self._flaresolverr:
            return super().set_cookie_auto(force_refresh)

        from nassav.models import SourceCookie

        source_name = self.get_source_name()

        if not force_refresh:
            try:
                cookie_obj = SourceCookie.objects.get(source_name=source_name)
                self.cookie = cookie_obj.cookie
                logger.info(f"{source_name}: 从数据库加载 cookie")
                return True
            except SourceCookie.DoesNotExist:
                logger.info(f"{source_name}: 数据库中无 cookie，通过 FlareSolverr 获取")

        home_url = f"https://{self.domain}/"
        cookie_str = self._flaresolverr.get_cookies_str(home_url)
        if not cookie_str:
            logger.warning(f"{source_name}: FlareSolverr 获取 cookie 失败，回退到 curl_cffi")
            return super().set_cookie_auto(force_refresh=True)

        SourceCookie.objects.update_or_create(
            source_name=source_name, defaults={"cookie": cookie_str}
        )
        self.cookie = cookie_str
        logger.info(f"{source_name}: FlareSolverr cookie 已保存到数据库")
        return True

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
