"""
Scraper 基类 - 定义刮削器的通用接口和方法
"""
from typing import Optional

from curl_cffi import requests
from loguru import logger


# 通用请求头
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 "
                  "Safari/537.36 Edg/143.0.0.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,"
              "application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6"
}


class ScraperBase:
    """刮削器基类"""

    def __init__(self, proxy: Optional[str] = None, timeout: int = 15):
        self.proxy = proxy
        self.proxies = {'http': proxy, 'https': proxy} if proxy else None
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
                impersonate="chrome110",
            )
            response.raise_for_status()
            return response.text
        except Exception as e:
            logger.error(f"Scraper 请求失败: {str(e)}")
            return None

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
