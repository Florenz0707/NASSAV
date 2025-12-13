import json
from pathlib import Path
from typing import Dict, List, Tuple, Optional

from django.conf import settings
from loguru import logger

from nassav.downloader import MissAVDownloader, JableDownloader, HohojDownloader, MemoDownloader, \
    KanavDownloader, AvtodayDownloader, NetflavDownloader, KissavDownloader, DownloaderBase
from nassav.scraper import ScraperManager, AVDownloadInfo


class DownloaderManager:
    """下载器管理器"""

    # 下载器类映射
    DOWNLOADER_CLASSES = {
        'missav': MissAVDownloader,
        'jable': JableDownloader,
        'hohoj': HohojDownloader,
        'memo': MemoDownloader,
        'kanav': KanavDownloader,
        'avtoday': AvtodayDownloader,
        'netflav': NetflavDownloader,
        'kissav': KissavDownloader,
    }

    def __init__(self):
        proxy = settings.PROXY_URL if settings.PROXY_ENABLED else None
        self.downloaders: Dict[str, DownloaderBase] = {}

        # 初始化元数据刮削器
        self.scraper = ScraperManager(proxy)

        # 注册下载器，根据配置中的权重
        source_config = settings.SOURCE_CONFIG

        for source_name, downloader_class in self.DOWNLOADER_CLASSES.items():
            config = source_config.get(source_name, {})
            weight = config.get('weight')
            # 只有配置了有效权重的源才会被注册
            if weight:
                downloader = downloader_class(proxy)
                # 从配置中读取并设置 cookie
                cookie = config.get('cookie')
                if cookie:
                    downloader.set_cookie(cookie)
                    logger.debug(f"注册下载器: {downloader.get_downloader_name()}, 权重: {weight}, Cookie: 已设置")
                else:
                    logger.debug(f"注册下载器: {downloader.get_downloader_name()}, 权重: {weight}")
                self.downloaders[downloader.get_downloader_name()] = downloader

    def get_sorted_downloaders(self) -> List[Tuple[str, DownloaderBase]]:
        """获取按权重排序的下载器列表"""
        source_config = settings.SOURCE_CONFIG
        sorted_items = []
        for name, downloader in self.downloaders.items():
            weight = source_config.get(name.lower(), {}).get('weight', 0)
            sorted_items.append((name, downloader, weight))
        sorted_items.sort(key=lambda x: x[2], reverse=True)
        return [(name, dl) for name, dl, _ in sorted_items]

    def get_info_from_any_source(self, avid: str) -> Optional[Tuple[AVDownloadInfo, DownloaderBase, str]]:
        """
        遍历所有源获取信息
        返回: (info, downloader, html) 或 None
        """
        import time
        for name, downloader in self.get_sorted_downloaders():
            logger.info(f"尝试从 {name} 获取 {avid}")
            html = downloader.get_html(avid)
            time.sleep(0.5)
            if html:
                info = downloader.parse_html(html)
                if info:
                    info.avid = avid.upper()
                    return info, downloader, html
        return None

    def get_resource_dir(self, avid: str) -> Path:
        """获取资源目录路径"""
        resource_dir = settings.RESOURCE_DIR / avid.upper()
        resource_dir.mkdir(parents=True, exist_ok=True)
        return resource_dir

    def save_all_resources(self, avid: str, info: AVDownloadInfo, downloader: DownloaderBase, html: str) -> dict:
        """
        一次性保存所有资源到 resource/{avid}/ 目录
        包括: HTML缓存、封面、元数据
        返回保存状态
        """
        avid = avid.upper()
        resource_dir = self.get_resource_dir(avid)
        result = {
            'html_saved': False,
            'cover_saved': False,
            'metadata_saved': False,
            'scraped': False,
        }

        # 1. 保存 HTML
        try:
            html_path = resource_dir / f"{avid}.html"
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html)
            logger.debug(f"HTML 已保存: {html_path}")
            result['html_saved'] = True
        except Exception as e:
            logger.error(f"保存 HTML 失败: {e}")

        # 2. 下载封面
        cover_url = downloader.get_cover_url(html)
        if cover_url:
            logger.info(f"封面下载地址: {cover_url}")
            cover_path = resource_dir / f"{avid}.jpg"
            if downloader.download_file(cover_url, str(cover_path)):
                result['cover_saved'] = True
            else:
                logger.warning(f"封面下载失败: {avid}")
        else:
            logger.warning(f"未找到封面URL: {avid}")

        # 3. 从刮削器获取额外元数据
        scraped_data = self.scraper.scrape(avid)
        if scraped_data:
            info.update_from_scrapper(scraped_data)
            result['scraped'] = True
            logger.info(f"已从刮削器获取 {avid} 的额外元数据")

        # 4. 保存元数据
        try:
            metadata_path = resource_dir / f"{avid}.json"
            info.to_json(str(metadata_path))
            result['metadata_saved'] = True
            logger.debug(f"元数据已保存: {metadata_path}")
        except Exception as e:
            logger.error(f"保存元数据失败: {e}")

        return result

    def load_cached_html(self, avid: str) -> Optional[str]:
        """从缓存加载 HTML"""
        avid = avid.upper()
        html_path = settings.RESOURCE_DIR / avid / f"{avid}.html"
        if html_path.exists():
            try:
                with open(html_path, 'r', encoding='utf-8') as f:
                    return f.read()
            except Exception as e:
                logger.error(f"读取缓存 HTML 失败: {e}")
        return None

    def load_cached_metadata(self, avid: str) -> Optional[AVDownloadInfo]:
        """从缓存加载元数据"""
        avid = avid.upper()
        metadata_path = settings.RESOURCE_DIR / avid / f"{avid}.json"
        if metadata_path.exists():
            try:
                with open(metadata_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    info = AVDownloadInfo(
                        m3u8=data.get('m3u8', ''),
                        title=data.get('title', ''),
                        avid=data.get('avid', ''),
                        source=data.get('source', '')
                    )
                    return info
            except Exception as e:
                logger.error(f"读取缓存元数据失败: {e}")
        return None


downloader_manager = DownloaderManager()
