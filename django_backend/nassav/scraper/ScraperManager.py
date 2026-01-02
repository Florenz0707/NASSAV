"""
Scraper 管理器 - 管理所有刮削器的注册和调用
"""
from typing import Dict, List, Optional, Tuple

from django.conf import settings
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
        """
        遍历所有刮削器获取元数据
        返回第一个成功获取的元数据
        """
        avid = avid.upper()
        for name, scraper in self.get_scrapers():
            metadata = scraper.scrape(avid)
            if metadata:
                return metadata
        logger.warning(f"无法从任何刮削源获取 {avid} 的元数据")
        return None

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
