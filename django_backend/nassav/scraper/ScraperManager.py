"""
Scraper 管理器 - 管理所有刮削器的注册和调用
"""

from typing import Dict, List, Optional, Tuple

from django.conf import settings
from django.core.cache import cache
from loguru import logger

from .Javbus import Busdmm, Dmmsee, Javbus
from .ScraperBase import ScraperBase


class ScraperManager:
    """刮削器管理器"""

    # 刮削器类映射
    SCRAPER_CLASSES = {
        "javbus": Javbus,
        "busdmm": Busdmm,
        "dmmsee": Dmmsee,
    }

    def __init__(self, proxy: Optional[str] = None):
        self.proxy = proxy
        self.scrapers: Dict[str, ScraperBase] = {}

        # 注册刮削器，根据配置
        scraper_config = settings.SCRAPER_CONFIG

        for scraper_name, scraper_class in self.SCRAPER_CLASSES.items():
            config = scraper_config.get(scraper_name, {})
            domain = config.get("domain")
            # 只有配置了域名的刮削器才会被注册
            if domain:
                scraper = scraper_class(proxy)
                self.scrapers[scraper.get_scraper_name()] = scraper

    def get_scrapers(self) -> List[Tuple[str, ScraperBase]]:
        """获取所有已注册的刮削器列表"""
        return [(name, scraper) for name, scraper in self.scrapers.items()]

    def scrape(self, avid: str) -> Optional[dict]:
        metadata, _ = self.scrape_with_source(avid)
        return metadata

    def scrape_with_source(self, avid: str) -> tuple[Optional[dict], Optional[str]]:
        """
        遍历所有刮削器获取元数据
        返回第一个成功获取的元数据

        使用缓存提高性能，减少外部请求
        """
        avid = avid.upper()
        cache_key = f"scraper_metadata:{avid}"

        # 尝试从缓存获取
        cached_metadata = cache.get(cache_key)
        if cached_metadata:
            logger.info(f"从缓存获取 {avid} 的元数据")
            if isinstance(cached_metadata, dict) and "metadata" in cached_metadata:
                return cached_metadata.get("metadata"), cached_metadata.get(
                    "scraper_name"
                )
            return cached_metadata, None

        # 缓存未命中，遍历刮削器
        for name, scraper in self.get_scrapers():
            metadata = scraper.scrape(avid)
            if metadata:
                # 缓存元数据
                try:
                    cache.set(
                        cache_key,
                        {
                            "metadata": metadata,
                            "scraper_name": name,
                        },
                        timeout=3600,
                    )  # 缓存1小时
                    logger.info(f"已缓存 {avid} 的元数据")
                except Exception as e:
                    logger.warning(f"缓存元数据失败: {e}")

                return metadata, name

        logger.warning(f"无法从任何刮削源获取 {avid} 的元数据")
        return None, None

    def download_cover(
        self,
        url: str,
        save_path: str,
        scraper_name: str | None = None,
    ) -> bool:
        """下载封面图片

        Args:
            url: 封面图片URL
            save_path: 保存路径
            scraper_name: 指定使用的 scraper 名称

        Returns:
            bool: 下载成功返回True，否则返回False
        """
        if scraper_name:
            scraper = self.scrapers.get(scraper_name)
            if scraper:
                return scraper.download_cover(url, save_path)

        last_successful_scraper = getattr(self, "_last_successful_scraper", None)
        if last_successful_scraper is not None:
            return last_successful_scraper.download_cover(url, save_path)

        # 如果没有成功的scraper记录，尝试使用第一个注册的scraper
        scrapers = self.get_scrapers()
        if scrapers:
            _, scraper = scrapers[0]
            return scraper.download_cover(url, save_path)

        logger.warning("没有可用的刮削器来下载封面")
        return False

    def scrape_from_specific(self, avid: str, scraper_name: str) -> Optional[dict]:
        """
        从指定的刮削器获取元数据
        """
        avid = avid.upper()
        scraper = self.scrapers.get(scraper_name)
        if scraper:
            return scraper.scrape(avid)
        logger.warning(f"刮削器 {scraper_name} 未注册")
        return None


# 创建模块级单例
proxy = settings.PROXY_URL if settings.PROXY_ENABLED else None
scraper_manager = ScraperManager(proxy)
