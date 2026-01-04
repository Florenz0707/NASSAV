"""
Scraper 基类 - 定义刮削器的通用接口和方法
"""
from typing import Optional

from curl_cffi import requests
from loguru import logger
from nassav.constants import HEADERS, IMPERSONATE


class ScraperBase:
    """刮削器基类"""

    def __init__(self, proxy: Optional[str] = None, timeout: int = 15):
        self.proxy = proxy
        self.proxies = {"http": proxy, "https": proxy} if proxy else None
        self.timeout = timeout
        self.domain = ""

    def set_domain(self, domain: str):
        """设置域名"""
        self.domain = domain

    def get_scraper_name(self) -> str:
        """获取刮削器名称，子类必须实现"""
        raise NotImplementedError

    def get_html(self, avid: str) -> Optional[str]:
        """根据 avid 获取 HTML，子类必须实现"""
        raise NotImplementedError

    def parse_html(self, html: str, avid: str) -> Optional[dict]:
        """解析 HTML 获取元数据，子类必须实现"""
        raise NotImplementedError

    def fetch_html(self, url: str) -> Optional[str]:
        """获取 HTML 页面"""
        logger.debug(f"Scraper fetch url: {url}")
        try:
            response = requests.get(
                url,
                proxies=self.proxies,
                headers=HEADERS,
                timeout=self.timeout,
                impersonate=IMPERSONATE,
            )
            response.raise_for_status()
            return response.text
        except Exception as e:
            logger.error(f"Scraper 请求失败: {str(e)}")
            return None

    def download_cover(self, url: str, save_path: str) -> bool:
        """下载封面图片（带Referer头）

        Args:
            url: 封面图片URL
            save_path: 保存路径

        Returns:
            bool: 下载成功返回True，否则返回False
        """
        import os

        try:
            # 设置请求头（包含Referer）
            headers = HEADERS.copy()
            headers["Referer"] = f"https://{self.domain}/"

            response = requests.get(
                url,
                headers=headers,
                proxies=self.proxies,
                timeout=self.timeout,
                impersonate=IMPERSONATE,
                stream=True,
            )
            response.raise_for_status()

            # 确保目录存在
            os.makedirs(os.path.dirname(save_path), exist_ok=True)

            # 写入文件
            with open(save_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

            logger.info(f"封面下载成功: {os.path.basename(save_path)}")
            return True

        except Exception as e:
            logger.warning(f"封面下载失败: {e}")
            return False

    def download_avatar(self, url: str, dest_path: str, max_retries: int = 3) -> bool:
        """下载演员头像图片（子类必须实现）

        Args:
            url: 头像图片URL
            dest_path: 目标文件路径
            max_retries: 最大重试次数

        Returns:
            bool: 下载成功返回True，否则返回False
        """
        raise NotImplementedError("子类必须实现 download_avatar 方法")

    def scrape(self, avid: str) -> Optional[dict]:
        """
        刮削元数据
        返回包含元数据的字典或 None
        """
        avid = avid.upper()
        logger.info(f"尝试从 {self.get_scraper_name()} ({self.domain}) 刮削 {avid} 的元数据")
        html = self.get_html(avid)
        if html:
            metadata = self.parse_html(html, avid)
            if metadata:
                logger.info(f"成功从 {self.get_scraper_name()} 获取 {avid} 的元数据")
                return metadata
        return None
