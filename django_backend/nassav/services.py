"""
服务层：封装下载器和刮削器逻辑
"""
from typing import Optional

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

# 导入常量（为了向后兼容，重新导出HEADERS）
from nassav.constants import HEADERS
from nassav.source.SourceManager import SourceManager, source_manager
from nassav.m3u8downloader import M3u8DownloaderBase, N_m3u8DL_RE


class VideoDownloadService:
    """视频下载服务"""

    def __init__(
            self,
            resource_manager: SourceManager,
            m3u8_downloader: M3u8DownloaderBase
    ):
        """
        初始化视频下载服务

        Args:
            resource_manager: 资源管理器（获取元数据、封面等）
            m3u8_downloader: M3U8 下载器（下载视频流）
        """
        self.manager = resource_manager
        self.m3u8_downloader = m3u8_downloader

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

        # 解析视频时长（用于日志显示）
        duration_seconds = self._parse_duration(info.duration) if info.duration else None

        # 下载m3u8视频（使用 Redis 分布式锁确保只有一个下载任务运行）
        result = self._download_m3u8(info.m3u8, avid, domain, duration_seconds)
        logger.info(f"[{avid}] 下载{'成功' if result else '失败'}")
        return result

    def _parse_duration(self, duration_str: str) -> Optional[int]:
        """解析时长字符串，返回秒数"""
        import re
        if not duration_str:
            return None
        # 尝试匹配 "120分钟" 或 "120分" 格式
        match = re.search(r'(\d+)分', duration_str)
        if match:
            return int(match.group(1)) * 60
        # 尝试匹配纯数字
        match = re.search(r'(\d+)', duration_str)
        if match:
            return int(match.group(1)) * 60
        return None

    def _get_domain_from_source(self, source: str) -> str:
        """根据 downloader 名称获取对应的 domain"""
        source_lower = source.lower()
        source_config = settings.SOURCE_CONFIG.get(source_lower, {})
        return source_config.get('domain', source_lower + '.com')

    def _download_m3u8(self, url: str, avid: str, domain: str, total_duration: Optional[int] = None) -> bool:
        """使用注入的 M3U8 下载器下载视频"""
        avid_upper = avid.upper()
        resource_dir = settings.RESOURCE_DIR / avid_upper

        duration_str = f"{total_duration // 60}分钟" if total_duration else "未知"
        logger.info(f"开始下载 {avid_upper} (预计时长: {duration_str})")
        logger.info(f"使用下载器: {self.m3u8_downloader.get_downloader_name()}")

        # 调用注入的 M3U8 下载器
        success = self.m3u8_downloader.download(
            url=url,
            output_dir=resource_dir,
            output_name=avid_upper,
            referer=f"https://{domain}/",
            user_agent=HEADERS["User-Agent"],
            thread_count=32,
            retry_count=5,
        )

        if success:
            # 确保输出文件为 MP4 格式
            self.m3u8_downloader.ensure_mp4(resource_dir, avid_upper)

        return success


# 全局服务实例（使用依赖注入）
video_download_service = VideoDownloadService(
    resource_manager=source_manager,
    m3u8_downloader=N_m3u8DL_RE(
        proxy=settings.PROXY_URL if settings.PROXY_ENABLED else None
    )
)
