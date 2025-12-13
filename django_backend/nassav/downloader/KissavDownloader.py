import re
from typing import Optional

from django.conf import settings
from loguru import logger

from nassav.scraper.AVDownloadInfo import AVDownloadInfo
from nassav.downloader.DownloaderBase import DownloaderBase


class KissavDownloader(DownloaderBase):
    """Kissav下载器"""

    def __init__(self, proxy: Optional[str] = None, timeout: int = 15):
        super().__init__(proxy, timeout)
        source_config = settings.SOURCE_CONFIG.get('kissav', {})
        self.domain = source_config.get('domain', 'f15.bzraizy.cc')

    def get_downloader_name(self) -> str:
        return "Kissav"

    def get_html(self, avid: str) -> Optional[str]:
        avid_lower = avid.lower()
        avid_upper = avid.upper()
        urls = [
            f'https://{self.domain}/video/{avid_lower}',
            f'https://{self.domain}/video/{avid_upper}',
            f'https://{self.domain}/{avid_lower}',
            f'https://{self.domain}/play/{avid_lower}',
            f"https://{self.domain}/videos/index/id/{avid_lower}",
        ]
        for url in urls:
            content = self.fetch_html(url)
            if content:
                return content
        return None

    def parse_html(self, html: str) -> Optional[AVDownloadInfo]:
        info = AVDownloadInfo()
        info.source = self.get_downloader_name()

        try:
            # 提取m3u8
            m3u8_patterns = [
                r'source:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
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
            title_patterns = [
                r'<meta property="og:title" content="([^"]+)"',
                r'<title>([^<]+)</title>',
                r'<h1[^>]*>([^<]+)</h1>',
            ]
            for pattern in title_patterns:
                match = re.search(pattern, html)
                if match:
                    info.title = match.group(1).strip()
                    break

            # 提取avid
            avid_match = re.search(r'([A-Z]+-\d+)', info.title, re.IGNORECASE)
            if avid_match:
                info.avid = avid_match.group(1).upper()

            return info
        except Exception as e:
            logger.error(f"Kissav解析失败: {e}")
            return None

    def get_cover_url(self, html: str) -> Optional[str]:
        try:
            match = re.search(r'<meta property="og:image" content="([^"]+)"', html)
            if match:
                return match.group(1)
            return None
        except Exception as e:
            logger.error(f"封面URL提取失败: {e}")
            return None
