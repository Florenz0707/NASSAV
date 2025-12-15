import re
from typing import Optional

from django.conf import settings
from loguru import logger

from nassav.scraper.AVDownloadInfo import AVDownloadInfo
from nassav.source.SourceBase import SourceBase


class Netflav(SourceBase):
    """Netflav下载器"""

    def __init__(self, proxy: Optional[str] = None, timeout: int = 15):
        super().__init__(proxy, timeout)
        source_config = settings.SOURCE_CONFIG.get('netflav', {})
        self.domain = source_config.get('domain', 'netflav.com')

    def get_source_name(self) -> str:
        return "Netflav"

    def get_html(self, avid: str) -> Optional[str]:
        # Netflav 使用搜索页面找到视频
        avid_lower = avid.lower()
        avid_upper = avid.upper()

        # 尝试直接访问视频页面
        urls = [
            f'https://{self.domain}/video/{avid_lower}',
            f'https://{self.domain}/video/{avid_upper}',
        ]
        for url in urls:
            content = self.fetch_html(url)
            if content:
                return content

        # 尝试搜索
        search_url = f'https://{self.domain}/search?keyword={avid_upper}'
        search_html = self.fetch_html(search_url)
        if search_html:
            # 从搜索结果中提取视频链接
            video_match = re.search(rf'href="([^"]+{avid_lower}[^"]*)"', search_html, re.IGNORECASE)
            if video_match:
                video_url = video_match.group(1)
                if not video_url.startswith('http'):
                    video_url = f'https://{self.domain}{video_url}'
                return self.fetch_html(video_url)

        return None

    def parse_html(self, html: str) -> Optional[AVDownloadInfo]:
        info = AVDownloadInfo()
        info.source = self.get_source_name()

        try:
            # Netflav 通常使用 iframe 或 ajax 加载视频
            # 尝试提取 m3u8
            m3u8_patterns = [
                r'downloader:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
                r'file:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
                r'hlsUrl\s*[=:]\s*["\']([^"\']+)["\']',
                r'm3u8["\']?\s*[:=]\s*["\']([^"\']+)["\']',
                r'["\']([^"\']+\.m3u8[^"\']*)["\']',
            ]
            for pattern in m3u8_patterns:
                match = re.search(pattern, html)
                if match:
                    info.m3u8 = match.group(1)
                    break

            if not info.m3u8:
                # 尝试提取 iframe src 并获取其中的 m3u8
                iframe_match = re.search(r'<iframe[^>]+src="([^"]+)"', html)
                if iframe_match:
                    iframe_url = iframe_match.group(1)
                    if not iframe_url.startswith('http'):
                        iframe_url = f'https:{iframe_url}' if iframe_url.startswith(
                            '//') else f'https://{self.domain}{iframe_url}'
                    iframe_html = self.fetch_html(iframe_url)
                    if iframe_html:
                        for pattern in m3u8_patterns:
                            match = re.search(pattern, iframe_html)
                            if match:
                                info.m3u8 = match.group(1)
                                break

            if not info.m3u8:
                return None

            # 提取标题
            title_match = re.search(r'<meta property="og:title" content="([^"]+)"', html)
            if title_match:
                info.title = title_match.group(1).strip()

            # 提取avid
            avid_match = re.search(r'([A-Z]+-\d+)', info.title, re.IGNORECASE)
            if avid_match:
                info.avid = avid_match.group(1).upper()

            return info
        except Exception as e:
            logger.error(f"Netflav解析失败: {e}")
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
