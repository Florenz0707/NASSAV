import re
from typing import Optional, Tuple

from curl_cffi import requests
from django.conf import settings
from loguru import logger

from nassav.scraper.AVDownloadInfo import AVDownloadInfo
from nassav.source.SourceBase import SourceBase


class MissAV(SourceBase):
    """MissAV下载器"""

    def __init__(self, proxy: Optional[str] = None, timeout: int = 15):
        super().__init__(proxy, timeout)
        source_config = settings.SOURCE_CONFIG.get('missav', {})
        self.domain = source_config.get('domain', 'missav.ai')

    def get_source_name(self) -> str:
        return "MissAV"

    def get_html(self, avid: str) -> Optional[str]:
        """根据avid获取HTML"""
        import time
        avid_lower = avid.lower()
        urls = [
            f'https://{self.domain}/cn/{avid_lower}-chinese-subtitle',
            f'https://{self.domain}/{avid_lower}-chinese-subtitle',
            f'https://{self.domain}/cn/{avid_lower}',
        ]
        for url in urls:
            content = self.fetch_html(url)
            time.sleep(0.5)
            if content:
                return content
        return None

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
                logger.debug(f"最高清晰度: {resolution}\nM3U8链接: {m3u8_url}")
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

    @staticmethod
    def _extract_uuid(html: str) -> Optional[str]:
        try:
            match = re.search(r"m3u8\|([a-f0-9|]+)\|com\|surrit\|https\|video", html)
            if match:
                return "-".join(match.group(1).split("|")[::-1])
            return None
        except Exception as e:
            logger.error(f"UUID提取异常: {str(e)}")
            return None

    @staticmethod
    def _extract_metadata(html: str, metadata: AVDownloadInfo) -> bool:
        """提取核心元数据：AVID 和标题"""
        try:
            og_title = re.search(r'<meta property="og:title" content="(.*?)"', html)
            if og_title:
                title_content = og_title.group(1)
                # 尝试从标题中分离 AVID
                code_match = re.search(r'^([A-Z]+(?:-[A-Z]+)*-\d+)', title_content)
                if code_match:
                    metadata.avid = code_match.group(1)
                    metadata.title = title_content.replace(metadata.avid, '').strip()
                else:
                    metadata.title = title_content.strip()
            return True
        except Exception as e:
            logger.error(f"核心元数据解析异常: {str(e)}")
            return False

    @staticmethod
    def _get_highest_quality_m3u8(playlist_url: str) -> Optional[Tuple[str, str]]:
        try:
            response = requests.get(playlist_url, timeout=10, impersonate="chrome110")
            response.raise_for_status()
            playlist_content = response.text

            streams = []
            pattern = re.compile(
                r'#EXT-X-STREAM-INF:BANDWIDTH=(\d+),.*?RESOLUTION=(\d+x\d+).*?\n(.*)'
            )

            for match in pattern.finditer(playlist_content):
                bandwidth = int(match.group(1))
                resolution = match.group(2)
                url = match.group(3).strip()
                streams.append((bandwidth, resolution, url))

            streams.sort(reverse=True, key=lambda x: x[0])
            logger.debug(streams)

            if streams:
                best_stream = streams[0]
                base_url = playlist_url.rsplit('/', 1)[0]
                full_url = f"{base_url}/{best_stream[2]}" if not best_stream[2].startswith('http') else best_stream[2]
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
