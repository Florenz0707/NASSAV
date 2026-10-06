import re

from django.conf import settings
from loguru import logger

from nassav.scraper.AVDownloadInfo import AVDownloadInfo
from nassav.source.SourceBase import SourceBase


class Memo(SourceBase):
    """MemoJav下载器"""

    def __init__(self, proxy: str | None = None, timeout: int = 15):
        super().__init__(proxy, timeout)
        source_config = settings.SOURCE_CONFIG.get("memo", {})
        self.domain = source_config.get("domain", "memojav.com")

    def get_source_name(self) -> str:
        return "Memo"

    def get_html(self, avid: str) -> str | None:
        avid_upper = avid.upper()
        urls = [
            f"https://{self.domain}/video/{avid_upper}",
            f"https://{self.domain}/cn/{avid_upper}",
            f"https://{self.domain}/{avid_upper}",
        ]
        for url in urls:
            content = self.fetch_html(url)
            if content:
                return content
        return None

    def parse_html(self, html: str) -> AVDownloadInfo | None:
        info = AVDownloadInfo()
        info.source = self.get_source_name()

        try:
            # 提取标题
            title_match = re.search(
                r'<meta property="og:title" content="([^"]+)"', html
            )
            if title_match:
                info.title = title_match.group(1).strip()

            # 提取avid
            avid_match = re.search(r"([A-Z]+-\d+)", info.title, re.IGNORECASE)
            if avid_match:
                info.avid = avid_match.group(1).upper()

            # 提取m3u8
            info.m3u8 = (
                f"https://video10.memojav.net/stream/{info.avid.upper()}/master.m3u8"
            )

            return info
        except Exception as e:
            logger.error(f"Memo解析失败: {e}")
            return None

    def get_cover_url(self, html: str) -> str | None:
        try:
            match = re.search(r'<meta property="og:image" content="([^"]+)"', html)
            if match:
                return match.group(1)
            return None
        except Exception as e:
            logger.error(f"封面URL提取失败: {e}")
            return None
