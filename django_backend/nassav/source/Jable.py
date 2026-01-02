import re
from typing import Optional

from django.conf import settings
from loguru import logger
from nassav.scraper.AVDownloadInfo import AVDownloadInfo
from nassav.source.SourceBase import SourceBase


class Jable(SourceBase):
    """Jable下载器"""

    def __init__(self, proxy: Optional[str] = None, timeout: int = 15):
        super().__init__(proxy, timeout)
        source_config = settings.SOURCE_CONFIG.get("jable", {})
        self.domain = source_config.get("domain", "jable.tv")

    def get_source_name(self) -> str:
        return "Jable"

    def get_html(self, avid: str) -> Optional[str]:
        url = f"https://{self.domain}/videos/{avid.lower()}/"
        return self.fetch_html(url)

    def parse_html(self, html: str) -> Optional[AVDownloadInfo]:
        """解析 HTML 获取核心下载信息（m3u8、avid、source_title）

        其他元数据（发行日期、时长、演员等）由 JavBus Scraper 提供
        """
        info = AVDownloadInfo()
        info.source = self.get_source_name()

        try:
            # 1. 提取 m3u8（必需）
            match = re.search(r'var hlsUrl = ["\']([^"\']+)["\']', html)
            if match:
                info.m3u8 = match.group(1)
            else:
                return None

            # 2. 提取 source_title（备用标题）- 优先从 <title> 标签提取
            # 格式: <title>AVID 标题内容 - Jable.TV | ...</title>
            title_match = re.search(r"<title>(.+?)\s*-\s*Jable\.TV", html)
            if title_match:
                full_title = title_match.group(1).strip()
                info.source_title = full_title

                # 3. 从标题中提取 AVID
                avid_match = re.match(r"^([A-Z]+-\d+)\s+(.+)$", full_title)
                if avid_match:
                    info.avid = avid_match.group(1)
                    info.source_title = avid_match.group(2).strip()

            # 如果标题提取失败，尝试其他模式
            if not info.source_title:
                title_patterns = [
                    r'<h4 class="title">([^<]+)</h4>',
                    r'<span class="font-medium">([^<]+)</span>',
                ]
                for pattern in title_patterns:
                    title_match = re.search(pattern, html)
                    if title_match:
                        info.source_title = title_match.group(1).strip()
                        break

            # 如果 AVID 还未提取，单独查找
            if not info.avid:
                avid_match = re.search(
                    r'<span class="inactive-color">([A-Z]+-\d+)</span>', html
                )
                if avid_match:
                    info.avid = avid_match.group(1)

            return info
        except Exception as e:
            logger.error(f"Jable 解析失败: {e}")
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
