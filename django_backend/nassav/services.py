"""
服务层：封装下载器和刮削器逻辑
"""

from pathlib import Path
from typing import Callable, Optional

from django.conf import settings
from loguru import logger

# 导入常量（为了向后兼容，重新导出HEADERS）
from nassav.constants import HEADERS
from nassav.m3u8downloader import M3u8DownloaderBase
from nassav.download_contracts import DownloadExecutor
from nassav.download_information import DownloadInfoResolver
from nassav.composition import build_video_download_service
from nassav.utils import parse_duration


class VideoDownloadService(DownloadExecutor):
    """视频下载服务"""

    def __init__(
        self, info_resolver: DownloadInfoResolver, m3u8_downloader: M3u8DownloaderBase
    ):
        self.info_resolver = info_resolver
        self.m3u8_downloader = m3u8_downloader

    def download_video(
        self,
        avid: str,
        progress_callback: Optional[Callable] = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> bool:
        """
        下载视频
        优先从缓存的元数据读取 m3u8 URL，避免重复 fetch_html

        Args:
            avid: 视频编号
            progress_callback: 进度回调函数
        """
        avid = avid.upper()
        resolved = self.info_resolver.resolve(avid)
        if resolved is None:
            return False
        info, domain = resolved.info, resolved.domain

        # 解析视频时长（用于日志显示）
        duration_seconds = parse_duration(info.duration) if info.duration else None

        # 下载m3u8视频（使用 Redis 分布式锁确保只有一个下载任务运行）
        result = self._download_m3u8(
            info.m3u8, avid, domain, duration_seconds, progress_callback, cancelled
        )
        logger.info(f"[{avid}] 视频下载{'成功' if result else '失败'}")
        return result

    def _download_m3u8(
        self,
        url: str,
        avid: str,
        domain: str,
        total_duration: Optional[int] = None,
        progress_callback: Optional[Callable] = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> bool:
        """使用注入的 M3U8 下载器下载视频"""
        avid_upper = avid.upper()
        # 输出到新的 VIDEO_DIR，文件命名为 {AVID}.mp4
        resource_dir = Path(settings.VIDEO_DIR)

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
            progress_callback=progress_callback,
            cancelled=cancelled,
        )

        if cancelled and cancelled():
            return False
        if success:
            # 确保输出文件为 MP4 格式
            self.m3u8_downloader.ensure_mp4(resource_dir, avid_upper)

        return success


# 全局服务实例（使用依赖注入）
video_download_service = build_video_download_service()
