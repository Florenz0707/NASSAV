import re
from typing import Optional

from django.conf import settings
from loguru import logger

from nassav.scraper.AVDownloadInfo import AVDownloadInfo
from nassav.downloader.DownloaderBase import DownloaderBase


class JableDownloader(DownloaderBase):
    """Jable下载器"""

    def __init__(self, proxy: Optional[str] = None, timeout: int = 15):
        super().__init__(proxy, timeout)
        source_config = settings.SOURCE_CONFIG.get('jable', {})
        self.domain = source_config.get('domain', 'jable.tv')

    def get_downloader_name(self) -> str:
        return "Jable"

    def get_html(self, avid: str) -> Optional[str]:
        url = f'https://{self.domain}/videos/{avid.lower()}/'
        return self.fetch_html(url)

    def parse_html(self, html: str) -> Optional[AVDownloadInfo]:
        info = AVDownloadInfo()
        info.source = self.get_downloader_name()

        try:
            # 提取m3u8
            match = re.search(r'var hlsUrl = ["\']([^"\']+)["\']', html)
            if match:
                info.m3u8 = match.group(1)
            else:
                return None

            # 提取标题 - 优先从 <title> 标签提取
            # 格式: <title>AVID 标题内容 - Jable.TV | ...</title>
            title_match = re.search(r'<title>(.+?)\s*-\s*Jable\.TV', html)
            if title_match:
                info.title = title_match.group(1).strip()
            else:
                # 回退到其他模式
                title_patterns = [
                    r'<h4 class="title">([^<]+)</h4>',  # 旧格式
                    r'<span>标题:</span>\s*<span class="font-medium">([^<]+)</span>',  # 新格式
                    r'<span class="font-medium">([^<]+)</span>',  # 简化格式
                ]
                for pattern in title_patterns:
                    title_match = re.search(pattern, html)
                    if title_match:
                        info.title = title_match.group(1).strip()
                        break

                # 提取avid
                avid_match = re.search(r'<span class="inactive-color">([A-Z]+-\d+)</span>', html)
                if avid_match:
                    info.avid = avid_match.group(1)

            return info
        except Exception as e:
            logger.error(f"Jable解析失败: {e}")
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
