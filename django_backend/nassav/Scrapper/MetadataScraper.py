import re
from typing import Optional

from curl_cffi import requests
from django.conf import settings
from loguru import logger

from nassav.services import HEADERS


class MetadataScraper:
    """
    元数据刮削器 - 从 JavBus 等网站获取详细元数据
    """

    def __init__(self, proxy: Optional[str] = None, timeout: int = 15):
        self.proxy = proxy
        self.proxies = {'http': proxy, 'https': proxy} if proxy else None
        self.timeout = timeout
        self.domains = settings.SCRAPPER_DOMAINS

    def fetch_html(self, url: str) -> Optional[str]:
        """获取 HTML"""
        logger.debug(f"Scrapper fetch url: {url}")
        try:
            response = requests.get(
                url,
                proxies=self.proxies,
                headers=HEADERS,
                timeout=self.timeout,
                impersonate="chrome110",
            )
            response.raise_for_status()
            return response.text
        except Exception as e:
            logger.error(f"Scrapper 请求失败: {str(e)}")
            return None

    def scrape(self, avid: str) -> Optional[dict]:
        """
        从配置的域名列表中尝试获取元数据
        返回包含元数据的字典
        """
        avid = avid.upper()
        for domain in self.domains:
            logger.info(f"尝试从 {domain} 刮削 {avid} 的元数据")
            url = f"https://{domain}/{avid}"
            html = self.fetch_html(url)
            if html:
                metadata = self.parse_javbus_html(html, avid)
                if metadata:
                    logger.info(f"成功从 {domain} 获取 {avid} 的元数据")
                    return metadata
        logger.warning(f"无法从任何刮削源获取 {avid} 的元数据")
        return None

    def parse_javbus_html(self, html: str, avid: str) -> Optional[dict]:
        """
        解析 JavBus 风格的 HTML 获取元数据
        """
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
