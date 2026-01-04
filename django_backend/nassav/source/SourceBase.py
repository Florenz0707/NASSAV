import os
from typing import Optional

from curl_cffi import requests
from curl_cffi.requests.exceptions import HTTPError
from loguru import logger
from nassav.constants import HEADERS, IMPERSONATE
from nassav.scraper.AVDownloadInfo import AVDownloadInfo


class SourceBase:
    """下载源基类

    Source 的职责：
    1. 提供 M3U8 视频流地址
    2. 提供 AVID 和标题
    3. 提供封面图片 URL

    不负责：
    - 详细元数据（发行日期、时长、演员等）由 Scraper（JavBus）提供
    """

    def __init__(self, proxy: Optional[str] = None, timeout: int = 15):
        self.proxy = proxy
        self.proxies = {"http": proxy, "https": proxy} if proxy else None
        self.cookie = None
        self.cookie_retry_times = 5
        self.timeout = timeout
        self.domain = ""

    def set_domain(self, domain: str):
        self.domain = domain

    def set_cookie(self, cookie: str):
        self.cookie = cookie

    def get_source_name(self) -> str:
        raise NotImplementedError

    def _get_home_url(self) -> str:
        """获取首页URL，用于cookie获取。子类可以重写此方法"""
        if not self.domain:
            raise ValueError(f"{self.get_source_name()} 未设置domain")
        return f"https://{self.domain}/"

    def set_cookie_auto(self, force_refresh: bool = False) -> bool:
        """
        自动获取cookie并存储到数据库

        Args:
            force_refresh: 是否强制刷新cookie，即使数据库中已存在

        Returns:
            bool: 是否成功获取并设置cookie
        """
        try:
            from time import sleep

            from nassav.models import SourceCookie

            source_name = self.get_source_name()

            # 如果不强制刷新，先尝试从数据库加载
            if not force_refresh:
                try:
                    cookie_obj = SourceCookie.objects.get(source_name=source_name)
                    self.cookie = cookie_obj.cookie
                    logger.info(f"{source_name}: 从数据库加载cookie")
                    return True
                except SourceCookie.DoesNotExist:
                    logger.info(f"{source_name}: 数据库中无cookie，开始自动获取")

            home_url = self._get_home_url()
            headers = HEADERS.copy()
            for i in range(self.cookie_retry_times):
                session = requests.Session()
                logger.info(f"{source_name}: 正在访问 {home_url} 获取cookie... 重试次数：{i + 1}")
                response = session.get(
                    home_url,
                    proxies=self.proxies,
                    headers=headers,
                    timeout=self.timeout,
                    impersonate=IMPERSONATE,
                )
                try:
                    response.raise_for_status()
                except HTTPError as err:
                    logger.info(f"{source_name}: 获取失败，进行重试...")
                    sleep(0.5)
                    continue

                # 获取cookie字符串
                cookies = session.cookies.get_dict()
                if not cookies:
                    logger.info(f"{source_name}: 获取失败，进行重试...")
                    sleep(0.5)
                else:
                    cookie_str = "; ".join([f"{k}={v}" for k, v in cookies.items()])
                    logger.info(f"{source_name}: 成功获取cookie: {list(cookies.keys())}")

                    SourceCookie.objects.update_or_create(
                        source_name=source_name, defaults={"cookie": cookie_str}
                    )
                    logger.info(f"{source_name}: Cookie已保存到数据库")
                    self.cookie = cookie_str
                    return True
        except Exception as e:
            logger.warning(f"{self.get_source_name()}: 自动获取cookie失败: {str(e)}")
            return False
        logger.warning(f"{source_name}：达到最大重试次数，cookie获取失败。")
        return False

    def load_cookie_from_db(self) -> bool:
        """
        从数据库加载cookie

        Returns:
            bool: 是否成功加载
        """
        try:
            from nassav.models import SourceCookie

            source_name = self.get_source_name()
            cookie_obj = SourceCookie.objects.get(source_name=source_name)
            self.cookie = cookie_obj.cookie
            logger.info(f"{source_name}: 从数据库加载cookie成功")
            return True
        except Exception as e:
            logger.warning(f"{self.get_source_name()}: 从数据库加载cookie失败: {str(e)}")
            return False

    def get_html(self, avid: str) -> Optional[str]:
        raise NotImplementedError

    def parse_html(self, html: str) -> Optional[AVDownloadInfo]:
        raise NotImplementedError

    def get_cover_url(self, html: str) -> str:
        raise NotImplementedError

    def fetch_html(self, url: str, referer: str = "") -> Optional[str]:
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
                impersonate=IMPERSONATE,
            )
            response.raise_for_status()
            return response.text
        except Exception as e:
            logger.error(f"请求失败: {str(e)}")
            return None

    def download_file(self, url: str, save_path: str, referer: str = "") -> bool:
        """下载文件到指定路径"""
        try:
            headers = HEADERS.copy()
            if referer:
                headers["Referer"] = referer
            if self.cookie:
                headers["Cookie"] = self.cookie
            response = requests.get(
                url,
                stream=True,
                impersonate=IMPERSONATE,
                proxies=self.proxies,
                headers=headers,
                timeout=self.timeout,
                allow_redirects=True,
            )
            response.raise_for_status()

            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            with open(save_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            return True
        except Exception as e:
            logger.error(f"下载失败: {e}")
            return False
