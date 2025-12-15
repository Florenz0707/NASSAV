"""
服务层：封装下载器和刮削器逻辑
"""
import os
import platform
import subprocess
import threading
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

# 通用请求头
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 "
                  "Safari/537.36 Edg/143.0.0.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,"
              "application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6"
}

from nassav.downloader.DownloaderManager import DownloaderManager, downloader_manager

# 全局下载锁 - 确保同时只有一个下载任务运行
_download_lock = threading.Lock()


class VideoDownloadService:
    """视频下载服务"""

    def __init__(self, downloader: DownloaderManager):
        self.manager = downloader

        # N_m3u8DL-RE 工具路径
        tools_dir = settings.BASE_DIR / "tools"
        if platform.system() == 'Windows':
            self.download_tool = str(tools_dir / "N_m3u8DL-RE.exe")
        else:
            self.download_tool = str(tools_dir / "N_m3u8DL-RE")

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

        # 下载m3u8视频（使用全局锁确保只有一个下载任务运行）
        with _download_lock:
            logger.debug(f"获取下载锁，开始下载 {avid}")
            result = self._download_m3u8(info.m3u8, avid, domain, duration_seconds)
            logger.debug(f"释放下载锁，{avid} 下载{'成功' if result else '失败'}")
            return result

    def _parse_duration(self, duration_str: str) -> Optional[int]:
        """解析时长字符串，返回秒数"""
        import re
        if not duration_str:
            return None
        # 尝试匹配 "120分钟" 或 "120分" 格式
        match = re.search(r'(\d+)\s*分', duration_str)
        if match:
            return int(match.group(1)) * 60
        # 尝试匹配纯数字
        match = re.search(r'(\d+)', duration_str)
        if match:
            return int(match.group(1)) * 60
        return None

    def _get_domain_from_source(self, source: str) -> str:
        """根据 source 名称获取对应的 domain"""
        source_lower = source.lower()
        source_config = settings.SOURCE_CONFIG.get(source_lower, {})
        return source_config.get('domain', source_lower + '.com')

    def _download_m3u8(self, url: str, avid: str, domain: str, total_duration: Optional[int] = None) -> bool:
        """使用 N_m3u8DL-RE 下载 m3u8 视频"""
        avid_upper = avid.upper()
        resource_dir = settings.RESOURCE_DIR / avid_upper
        resource_dir.mkdir(parents=True, exist_ok=True)
        mp4_path = resource_dir / f"{avid_upper}.mp4"
        tmp_path = resource_dir / "temp"

        try:
            # 构建 N_m3u8DL-RE 命令
            user_agent = (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36"
            )

            cmd = [
                self.download_tool,
                url,
                "--tmp-dir", str(tmp_path),
                "--save-dir", str(resource_dir),
                "--save-name", avid_upper,
                "--thread-count", "32",  # 并发下载线程数
                "--download-retry-count", "5",  # 重试次数
                "--del-after-done",  # 下载完成后删除临时文件
                "--auto-select",  # 自动选择最佳质量
                "--no-log",  # 禁用日志文件
                "-H", f"Referer: https://{domain}/",
                "-H", f"User-Agent: {user_agent}",
            ]

            duration_str = f"{total_duration // 60}分钟" if total_duration else "未知"
            logger.info(f"开始下载 {avid_upper} (预计时长: {duration_str})")
            logger.debug(f"执行命令: {' '.join(cmd)}")

            # 设置环境变量
            env = os.environ.copy()
            if settings.PROXY_ENABLED and settings.PROXY_URL:
                env['http_proxy'] = settings.PROXY_URL
                env['https_proxy'] = settings.PROXY_URL
                env['HTTP_PROXY'] = settings.PROXY_URL
                env['HTTPS_PROXY'] = settings.PROXY_URL
                logger.debug(f"使用代理: {settings.PROXY_URL}")

            # 直接运行，让工具输出到终端显示进度
            result = subprocess.run(
                cmd,
                env=env,
                capture_output=False,  # 不捕获输出，直接显示到终端
            )

            if result.returncode != 0:
                logger.error(f"N_m3u8DL-RE 下载失败，退出码: {result.returncode}")
                return False

            # 检查输出文件
            # N_m3u8DL-RE 可能生成 .mp4 或 .ts 文件
            possible_files = [
                resource_dir / f"{avid_upper}.mp4",
                resource_dir / f"{avid_upper}.ts",
                resource_dir / f"{avid_upper}.mkv",
            ]

            output_file = None
            for f in possible_files:
                if f.exists():
                    output_file = f
                    break

            if output_file:
                file_size = output_file.stat().st_size
                size_mb = file_size / (1024 * 1024)

                # 如果不是 mp4，重命名为 mp4
                if output_file.suffix != '.mp4':
                    output_file.rename(mp4_path)
                    logger.debug(f"重命名 {output_file.name} -> {avid_upper}.mp4")

                logger.info(f"[{avid_upper}] 下载完成: {size_mb:.1f} MB")
                return True
            else:
                logger.error(f"[{avid_upper}] 未找到输出文件")
                return False

        except FileNotFoundError:
            logger.error(f"N_m3u8DL-RE 工具不存在: {self.download_tool}")
            return False
        except Exception as e:
            logger.error(f"下载失败: {e}")
            return False


# 全局服务实例
video_download_service = VideoDownloadService(downloader_manager)
