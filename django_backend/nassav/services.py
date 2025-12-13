"""
服务层：封装下载器和刮削器逻辑
"""
import json
import os
import platform
from pathlib import Path
from typing import Optional, Tuple, List, Dict

from django.conf import settings
from loguru import logger

# 初始化日志
LOG_DIR = settings.LOG_DIR
logger.add(
    str(LOG_DIR / "{time:YYYY-MM-DD}.log"),
    rotation="00:00",
    retention="7 days",
    enqueue=False,
    level="DEBUG",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}"
)

# 通用请求头
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 "
                  "Safari/537.36 Edg/143.0.0.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,"
              "application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6"
}

from nassav.Scrapper.AVDownloadInfo import AVDownloadInfo
from nassav.Scrapper.MetadataScrapper import MetadataScrapper
from nassav.downloader.DownloaderBase import DownloaderBase

from nassav.downloader.AvtodayDownloader import AvtodayDownloader
from nassav.downloader.KanavDownloader import KanavDownloader
from nassav.downloader.KissavDownloader import KissavDownloader
from nassav.downloader.MemoDownloader import MemoDownloader
from nassav.downloader.MissAVDownloader import MissAVDownloader
from nassav.downloader.HohojDownloader import HohojDownloader
from nassav.downloader.JableDownloader import JableDownloader
from nassav.downloader.NetflavDownloader import NetflavDownloader


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
        self.scrapper = MetadataScrapper(proxy)

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
            'cover_path': None
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
                result['cover_path'] = (str(cover_path) is None)
            else:
                logger.warning(f"封面下载失败: {avid}")
        else:
            logger.warning(f"未找到封面URL: {avid}")

        # 3. 从刮削器获取额外元数据
        scrapped_data = self.scrapper.scrape(avid)
        if scrapped_data:
            info.update_from_scrapper(scrapped_data)
            result['scrapped'] = True
            logger.info(f"已从刮削器获取 {avid} 的额外元数据")
        else:
            result['scrapped'] = False

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


class VideoDownloadService:
    """视频下载服务"""

    def __init__(self, downloader: DownloaderManager):
        self.manager = downloader

        # 下载工具路径
        tools_dir = settings.BASE_DIR / "tools"
        if platform.system() == 'Windows':
            self.download_tool = str(tools_dir / "m3u8-Downloader-Go.exe")
            self.ffmpeg_tool = str(tools_dir / "ffmpeg.exe")
        else:
            self.download_tool = str(tools_dir / "m3u8-Downloader-Go")
            self.ffmpeg_tool = "ffmpeg"

    def download_video(self, avid: str) -> bool:
        """
        下载视频
        优先从缓存的元数据读取 m3u8 URL，避免重复 fetch_html
        """
        avid = avid.upper()
        self.manager.get_resource_dir(avid)

        # 优先从缓存读取元数据
        info = self.manager.load_cached_metadata(avid)
        if info and info.m3u8:
            logger.info(f"从缓存读取 {avid} 的元数据")
            domain = self._get_domain_from_source(info.source)
        else:
            # 缓存不存在，重新获取
            logger.info(f"缓存不存在，重新获取 {avid} 的信息")
            result = self.manager.get_info_from_any_source(avid)
            if not result:
                logger.error(f"无法获取 {avid} 的下载信息")
                return False

            info, downloader, html = result
            domain = downloader.domain

            # 保存所有资源
            self.manager.save_all_resources(avid, info, downloader, html)

        # 下载m3u8视频
        if not self._download_m3u8(info.m3u8, avid, domain):
            return False

        return True

    def _get_domain_from_source(self, source: str) -> str:
        """根据 source 名称获取对应的 domain"""
        source_lower = source.lower()
        source_config = settings.SOURCE_CONFIG.get(source_lower, {})
        return source_config.get('domain', source_lower + '.com')

    def _download_m3u8(self, url: str, avid: str, domain: str) -> bool:
        """下载m3u8视频"""
        resource_dir = settings.RESOURCE_DIR / avid.upper()
        resource_dir.mkdir(parents=True, exist_ok=True)
        ts_path = resource_dir / f"{avid}.ts"
        mp4_path = resource_dir / f"{avid}.mp4"

        try:
            proxy = settings.PROXY_URL if settings.PROXY_ENABLED else None

            # 下载命令
            if proxy:
                command = f'"{self.download_tool}" -u {url} -o "{ts_path}" -p {proxy} -H Referer:http://{domain}'
            else:
                command = f'"{self.download_tool}" -u {url} -o "{ts_path}" -H Referer:http://{domain}'

            logger.debug(f"执行命令: {command}")
            if os.system(command) != 0:
                logger.error("m3u8下载失败")
                return False

            # 转换为mp4
            convert_cmd = f'"{self.ffmpeg_tool}" -i "{ts_path}" -c copy -f mp4 "{mp4_path}"'
            logger.debug(f"执行转换: {convert_cmd}")
            if os.system(convert_cmd) != 0:
                logger.error("mp4转换失败")
                return False

            # 删除ts文件
            if ts_path.exists():
                ts_path.unlink()

            return True
        except Exception as e:
            logger.error(f"下载失败: {e}")
            return False


# 全局服务实例
downloader_manager = DownloaderManager()
video_download_service = VideoDownloadService(downloader_manager)
