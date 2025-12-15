import re
from typing import Optional

from django.conf import settings
from loguru import logger

from nassav.scraper.AVDownloadInfo import AVDownloadInfo
from nassav.source.SourceBase import SourceBase


class Avtoday(SourceBase):
    """Avtoday下载器"""

    def __init__(self, proxy: Optional[str] = None, timeout: int = 15):
        super().__init__(proxy, timeout)
        source_config = settings.SOURCE_CONFIG.get('avtoday', {})
        self.domain = source_config.get('domain', 'avtoday.io')

    def get_source_name(self) -> str:
        return "Avtoday"

    def get_html(self, avid: str) -> Optional[str]:
        avid_lower = avid.lower()
        avid_upper = avid.upper()
        urls = [
            f'https://{self.domain}/video/{avid_lower}',
            f'https://{self.domain}/video/{avid_upper}',
            f'https://{self.domain}/watch/{avid_lower}',
            f'https://{self.domain}/{avid_lower}',
        ]
        for url in urls:
            content = self.fetch_html(url)
            if content:
                return content
        return None

    def parse_html(self, html: str) -> Optional[AVDownloadInfo]:
        info = AVDownloadInfo()
        info.source = self.get_source_name()

        try:
            # 提取m3u8 - Avtoday 特定格式: var m3u8_url = 'https://avtoday.io/streaming/XXX/xxx.m3u8';
            m3u8_patterns = [
                r"var\s+m3u8_url\s*=\s*['\"]([^'\"]+\.m3u8)['\"]",  # Avtoday 特定格式
                r'downloader:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
                r'file:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
                r'hlsUrl\s*[=:]\s*["\']([^"\']+)["\']',
                r'["\']([^"\']+\.m3u8[^"\']*)["\']',
            ]
            for pattern in m3u8_patterns:
                match = re.search(pattern, html)
                if match:
                    info.m3u8 = match.group(1)
                    break

            if not info.m3u8:
                return None

            # 提取标题
            title_match = re.search(r'<meta property="og:title" content="([^"]+)"', html)
            if title_match:
                info.title = title_match.group(1).strip()

            # 提取avid - 优先从 m3u8 URL 中提取
            avid_match = re.search(r'/streaming/([A-Z]+-\d+)/', info.m3u8, re.IGNORECASE)
            if avid_match:
                info.avid = avid_match.group(1).upper()
            elif info.title:
                avid_match = re.search(r'([A-Z]+-\d+)', info.title, re.IGNORECASE)
                if avid_match:
                    info.avid = avid_match.group(1).upper()

            return info
        except Exception as e:
            logger.error(f"Avtoday解析失败: {e}")
            return None

    def get_cover_url(self, html: str) -> Optional[str]:
        try:
            # Avtoday 特定格式: var cover = '/pic/2025/12/SONE-992-1764905152.jpg';
            cover_match = re.search(r"var\s+cover\s*=\s*['\"]([^'\"]+)['\"]", html)
            if cover_match:
                cover_path = cover_match.group(1)
                # 如果是相对路径，补全为完整 URL
                if cover_path.startswith('/'):
                    return f'https://{self.domain}{cover_path}'
                return cover_path

            # 回退到 og:image
            match = re.search(r'<meta property="og:image" content="([^"]+)"', html)
            if match:
                return match.group(1)
            return None
        except Exception as e:
            logger.error(f"封面URL提取失败: {e}")
            return None
