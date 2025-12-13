import os
from typing import Optional

from curl_cffi import requests
from loguru import logger

from nassav.scraper.AVDownloadInfo import AVDownloadInfo
from nassav.services import HEADERS


class DownloaderBase:
    """下载器基类"""

    def __init__(self, proxy: Optional[str] = None, timeout: int = 15):
        self.proxy = proxy
        self.proxies = {'http': proxy, 'https': proxy} if proxy else None
        self.cookie = None
        self.timeout = timeout
        self.domain = ""

    def set_domain(self, domain: str):
        self.domain = domain

    def set_cookie(self, cookie: str):
        self.cookie = cookie

    def get_downloader_name(self) -> str:
        raise NotImplementedError

    def get_html(self, avid: str) -> Optional[str]:
        raise NotImplementedError

    def parse_html(self, html: str) -> Optional[AVDownloadInfo]:
        raise NotImplementedError

    def get_cover_url(self, html: str) -> str:
        raise NotImplementedError

    def fetch_html(self, url: str, referer: str = "") -> Optional[str]:
        logger.debug(f"fetch url: {url}")
        try:
            headers = HEADERS.copy()
            if referer:
                headers["Referer"] = referer
            if self.cookie:
                headers["Cookie"] = self.cookie
            response = requests.get(
                url,
                proxies=self.proxies,
                headers=headers,
                timeout=self.timeout,
                impersonate="chrome110",
            )
            response.raise_for_status()
            return response.text
        except Exception as e:
            logger.error(f"请求失败: {str(e)}")
            return None

    def download_file(self, url: str, save_path: str, referer: str = "") -> bool:
        """下载文件到指定路径"""
        logger.debug(f"download {url} to {save_path}")
        try:
            headers = HEADERS.copy()
            if referer:
                headers["Referer"] = referer
            if self.cookie:
                headers["Cookie"] = self.cookie
            response = requests.get(
                url,
                stream=True,
                impersonate="chrome110",
                proxies=self.proxies,
                headers=headers,
                timeout=self.timeout,
                allow_redirects=True
            )
            response.raise_for_status()

            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            with open(save_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            return True
        except Exception as e:
            logger.error(f"下载失败: {e}")
            return False
