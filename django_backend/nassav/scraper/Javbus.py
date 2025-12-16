"""
JavBus 风格刮削器 - 适用于 JavBus 及其镜像站（Busdmm, Dmmsee 等）
"""
import re
from typing import Optional

from django.conf import settings
from loguru import logger

from .ScraperBase import ScraperBase


class Javbus(ScraperBase):
    """JavBus 刮削器"""

    def __init__(self, proxy: Optional[str] = None, timeout: int = 15):
        super().__init__(proxy, timeout)
        source_config = settings.SCRAPER_CONFIG.get('javbus', {})
        self.domain = source_config.get('domain', 'www.javbus.com')

    def get_scraper_name(self) -> str:
        return "Javbus"

    def get_html(self, avid: str) -> Optional[str]:
        avid = avid.upper()
        url = f"https://{self.domain}/{avid}"
        return self.fetch_html(url)

    def parse_html(self, html: str, avid: str) -> Optional[dict]:
        """解析 JavBus 风格的 HTML 获取元数据"""
        return self._parse_javbus_style_html(html, avid)

    def _parse_javbus_style_html(self, html: str, avid: str) -> Optional[dict]:
        """解析 JavBus 风格 HTML 的通用方法"""
        metadata = {
            'avid': avid,
            'title': '',
            'release_date': '',
            'duration': '',
            'director': '',
            'studio': '',
            'label': '',
            'series': '',
            'genres': [],
            'actors': []
        }

        try:
            # 从 meta description 提取基本信息
            # 格式: 【發行日期】2025-12-19，【長度】160分鐘，(ABF-296)「標題...」
            meta_match = re.search(r'<meta\s+name="description"\s+content="([^"]+)"', html)
            if meta_match:
                desc = meta_match.group(1)

                # 提取发行日期
                date_match = re.search(r'【發行日期】(\d{4}-\d{2}-\d{2})', desc)
                if date_match:
                    metadata['release_date'] = date_match.group(1)

                # 提取时长
                duration_match = re.search(r'【長度】(\d+)分鐘', desc)
                if duration_match:
                    metadata['duration'] = duration_match.group(1) + "分钟"

                # 提取标题 - (AVID)后面的内容
                title_match = re.search(rf'\({avid}\)(.+?)$', desc)
                if title_match:
                    metadata['title'] = title_match.group(1).strip()

            # 从页面标题提取标题（作为备选）
            if not metadata['title']:
                title_tag_match = re.search(r'<title>([^<]+)</title>', html)
                if title_tag_match:
                    title = title_tag_match.group(1)
                    # 移除网站名称后缀
                    title = re.sub(r'\s*[-|]\s*JavBus.*$', '', title, flags=re.IGNORECASE)
                    # 移除 AVID 前缀
                    title = re.sub(rf'^{avid}\s*', '', title, flags=re.IGNORECASE)
                    metadata['title'] = title.strip()

            # 提取导演
            director_match = re.search(r'導演:</span>\s*<a[^>]*>([^<]+)</a>', html)
            if director_match:
                metadata['director'] = director_match.group(1).strip()

            # 提取制作商
            studio_match = re.search(r'製作商:</span>\s*<a[^>]*>([^<]+)</a>', html)
            if studio_match:
                metadata['studio'] = studio_match.group(1).strip()

            # 提取发行商
            label_match = re.search(r'發行商:</span>\s*<a[^>]*>([^<]+)</a>', html)
            if label_match:
                metadata['label'] = label_match.group(1).strip()

            # 提取系列
            series_match = re.search(r'系列:</span>\s*<a[^>]*>([^<]+)</a>', html)
            if series_match:
                metadata['series'] = series_match.group(1).strip()

            # 提取类别
            genres = re.findall(r'<span class="genre"><a[^>]*>([^<]+)</a></span>', html)
            if genres:
                metadata['genres'] = [g.strip() for g in genres]

            # 提取演员
            actors = re.findall(r'<a class="avatar-box"[^>]*>\s*<span>([^<]+)</span>', html)
            if actors:
                metadata['actors'] = [a.strip() for a in actors]

            # 检查是否获取到了有效数据
            if metadata['release_date'] or metadata['title'] or metadata['actors']:
                return metadata

            return None

        except Exception as e:
            logger.error(f"解析 JavBus HTML 失败: {e}")
            return None


class Busdmm(Javbus):
    """Busdmm 刮削器 - JavBus 镜像站"""

    def __init__(self, proxy: Optional[str] = None, timeout: int = 15):
        super().__init__(proxy, timeout)
        source_config = settings.SCRAPER_CONFIG.get('busdmm', {})
        self.domain = source_config.get('domain', 'www.busdmm.ink')

    def get_scraper_name(self) -> str:
        return "Busdmm"


class Dmmsee(Javbus):
    """Dmmsee 刮削器 - JavBus 镜像站"""

    def __init__(self, proxy: Optional[str] = None, timeout: int = 15):
        super().__init__(proxy, timeout)
        source_config = settings.SCRAPER_CONFIG.get('dmmsee', {})
        self.domain = source_config.get('domain', 'www.dmmsee.bond')

    def get_scraper_name(self) -> str:
        return "Dmmsee"
