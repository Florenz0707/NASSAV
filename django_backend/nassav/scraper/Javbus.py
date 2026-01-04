"""
JavBus 风格刮削器 - 适用于 JavBus 及其镜像站（Busdmm, Dmmsee 等）
"""
import re
from typing import Optional

from curl_cffi import requests
from django.conf import settings
from loguru import logger
from nassav.constants import IMPERSONATE

from .ScraperBase import ScraperBase


class Javbus(ScraperBase):
    """JavBus 刮削器"""

    def __init__(self, proxy: Optional[str] = None, timeout: int = 15):
        super().__init__(proxy, timeout)
        source_config = settings.SCRAPER_CONFIG.get("javbus", {})
        self.domain = source_config.get("domain", "www.javbus.com")

    def get_scraper_name(self) -> str:
        return "Javbus"

    def get_html(self, avid: str) -> Optional[str]:
        avid = avid.upper()
        url = f"https://{self.domain}/{avid}"
        return self.fetch_html(url)

    def parse_html(self, html: str, avid: str) -> Optional[dict]:
        """解析 JavBus 风格的 HTML 获取元数据"""
        scrape_data = {
            "avid": avid.upper(),
            "title": "",
            "release_date": "",
            "duration": "",
            "studio": "",
            "label": "",
            "series": "",
            "genres": [],
            "actors": [],
        }

        try:
            # 从 meta description 提取基本信息
            # 格式: 【發行日期】2025-12-19，【長度】160分鐘，(ABF-296)「標題...」
            meta_match = re.search(
                r'<meta\s+name="description"\s+content="([^"]+)"', html
            )
            if meta_match:
                desc = meta_match.group(1)

                # 提取发行日期
                date_match = re.search(r"【發行日期】(\d{4}-\d{2}-\d{2})", desc)
                if date_match:
                    scrape_data["release_date"] = date_match.group(1)

                # 提取时长
                duration_match = re.search(r"【長度】(\d+)分鐘", desc)
                if duration_match:
                    scrape_data["duration"] = duration_match.group(1) + "分钟"

                # 提取标题 - (AVID)后面的内容
                title_match = re.search(rf"\({avid}\)(.+?)$", desc)
                if title_match:
                    scrape_data["title"] = title_match.group(1).strip()

            # 从页面内容提取发行日期（如果 meta 中没有）
            if not scrape_data["release_date"]:
                release_match = re.search(
                    r'<span class="header">發行日期:</span>\s*(\d{4}-\d{2}-\d{2})', html
                )
                if release_match:
                    scrape_data["release_date"] = release_match.group(1)

            # 从页面内容提取时长（如果 meta 中没有）
            if not scrape_data["duration"]:
                duration_match = re.search(
                    r'<span class="header">長度:</span>\s*(\d+)分鐘', html
                )
                if duration_match:
                    scrape_data["duration"] = duration_match.group(1) + "分钟"

            # 从页面标题提取标题（作为备选，仅当 meta 中未获取到时）
            if not scrape_data["title"]:
                title_tag_match = re.search(r"<title>([^<]+)</title>", html)
                if title_tag_match:
                    title = title_tag_match.group(1)
                    # 移除网站名称后缀
                    title = re.sub(
                        r"\s*[-|]\s*JavBus.*$", "", title, flags=re.IGNORECASE
                    )
                    # 移除 AVID 前缀（包括可能的空格）
                    title = re.sub(rf"^{avid}\s*", "", title, flags=re.IGNORECASE)
                    scrape_data["title"] = title.strip()

            # 提取製作商（studio）
            studio_match = re.search(
                r'<span class="header">製作商:</span>\s*<a[^>]*>([^<]+)</a>', html
            )
            if studio_match:
                scrape_data["studio"] = studio_match.group(1).strip()

            # 提取發行商（label）
            label_match = re.search(
                r'<span class="header">發行商:</span>\s*<a[^>]*>([^<]+)</a>', html
            )
            if label_match:
                scrape_data["label"] = label_match.group(1).strip()

            # 提取系列（series）
            series_match = re.search(
                r'<span class="header">系列:</span>\s*<a[^>]*>([^<]+)</a>', html
            )
            if series_match:
                scrape_data["series"] = series_match.group(1).strip()

            # 提取類別（categories）
            genres_matches = re.findall(
                r'<span class="genre"><label><input[^>]*><a[^>]*>([^<]+)</a></label></span>',
                html,
            )
            if genres_matches:
                # 过滤掉技术性标签
                technical_tags = [
                    "フルハイビジョン(FHD)",
                    "MGSだけのおまけ映像付き",
                    "高畫質",
                    "單體作品",
                    "DMM獨家",
                    "4K",
                    "薄馬賽克",
                    "數位馬賽克",
                    "企畫",
                    "纪录片",
                    "高",
                ]
                filtered_genres = [
                    cat for cat in genres_matches if cat not in technical_tags
                ]
                scrape_data["genres"] = filtered_genres

            # 提取導演（director）
            director_match = re.search(
                r'<span class="header">導演:</span>\s*<a[^>]*>([^<]+)</a>', html
            )
            if director_match:
                scrape_data["director"] = director_match.group(1).strip()

            # 提取封面URL
            cover_match = re.search(r'<a[^>]*class="bigImage"[^>]*href="([^"]+)"', html)
            if cover_match:
                cover_url = cover_match.group(1)
                # 将相对路径转为完整URL
                if cover_url.startswith("/"):
                    scrape_data["cover_url"] = f"https://{self.domain}{cover_url}"
                else:
                    scrape_data["cover_url"] = cover_url

            # 提取演員（actors）及头像URL
            # 从 img 标签的 title 属性提取演员名（完整名称）
            # 因为 span 标签中的名字可能被截断（如"めぐり（藤"）
            # 而 img title 中保存的是完整名字（如"めぐり（藤浦めぐ）"）
            # 同时提取src属性获取头像URL
            actor_pattern = re.compile(
                r'<a class="avatar-box"[^>]*>\s*<div[^>]*>\s*'
                r'<img[^>]*src="([^"]+)"[^>]*title="([^"]+)"[^>]*>',
                re.DOTALL,
            )
            actor_matches = actor_pattern.findall(html)
            if actor_matches:
                scrape_data["actors"] = [name for _, name in actor_matches]
                # 保存头像URL映射: {演员名: 完整URL}
                actor_avatars = {}
                for src, name in actor_matches:
                    # 将相对路径转为完整URL
                    if src.startswith("/"):
                        avatar_url = f"https://{self.domain}{src}"
                    else:
                        avatar_url = src
                    actor_avatars[name] = avatar_url
                scrape_data["actor_avatars"] = actor_avatars

            return scrape_data

        except Exception as e:
            logger.error(f"解析 JavBus HTML 失败: {e}")
            return None

    def download_avatar(self, url: str, dest_path: str, max_retries: int = 3) -> bool:
        """下载演员头像图片（JavBus 实现）

        Args:
            url: 头像图片URL
            dest_path: 目标文件路径
            max_retries: 最大重试次数

        Returns:
            bool: 下载成功返回True，否则返回False
        """
        from pathlib import Path

        from nassav.constants import HEADERS

        dest = Path(dest_path)
        dest.parent.mkdir(parents=True, exist_ok=True)

        # 设置请求头（模拟浏览器，添加Referer）
        headers = HEADERS.copy()
        headers["Referer"] = f"https://{self.domain}/"

        for attempt in range(max_retries):
            try:
                response = requests.get(
                    url,
                    headers=headers,
                    proxies=self.proxies,
                    timeout=self.timeout,
                    impersonate=IMPERSONATE,
                )
                if response.status_code == 200:
                    dest.write_bytes(response.content)
                    return True
                else:
                    logger.warning(f"头像下载失败 (HTTP {response.status_code}): {url}")
            except Exception as e:
                logger.warning(f"头像下载失败 (尝试 {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    import time

                    time.sleep(1)  # 重试前等待1秒

        return False


class Busdmm(Javbus):
    """Busdmm 刮削器 - JavBus 镜像站"""

    def __init__(self, proxy: Optional[str] = None, timeout: int = 15):
        super().__init__(proxy, timeout)
        source_config = settings.SCRAPER_CONFIG.get("busdmm", {})
        self.domain = source_config.get("domain", "www.busdmm.ink")

    def get_scraper_name(self) -> str:
        return "Busdmm"


class Dmmsee(Javbus):
    """Dmmsee 刮削器 - JavBus 镜像站"""

    def __init__(self, proxy: Optional[str] = None, timeout: int = 15):
        super().__init__(proxy, timeout)
        source_config = settings.SCRAPER_CONFIG.get("dmmsee", {})
        self.domain = source_config.get("domain", "www.dmmsee.bond")

    def get_scraper_name(self) -> str:
        return "Dmmsee"
