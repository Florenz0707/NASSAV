"""
服务层：封装下载器和刮削器逻辑
"""
import os
import platform

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

from nassav.downloader.DownloaderManager import DownloaderManager, downloader_manager


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
video_download_service = VideoDownloadService(downloader_manager)
