"""
服务层：封装下载器和刮削器逻辑
"""
import os
import time
from contextlib import contextmanager
from typing import Optional

import redis
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

from nassav.source.SourceManager import SourceManager, source_manager
from nassav.m3u8downloader import M3u8DownloaderBase, N_m3u8DL_RE

# Redis 分布式锁 - 跨进程有效
_redis_client = redis.from_url(settings.CELERY_BROKER_URL)
_DOWNLOAD_LOCK_KEY = "nassav:download_lock"
_TASK_QUEUE_KEY = "nassav:task_queue:{avid}"  # 每个avid的任务队列锁
_DOWNLOAD_LOCK_TIMEOUT = 7200  # 锁超时时间：2小时（防止死锁）
_TASK_QUEUE_TIMEOUT = 3600  # 任务队列锁超时时间：1小时


@contextmanager
def redis_download_lock(avid: str, timeout: int = _DOWNLOAD_LOCK_TIMEOUT):
    """
    Redis 分布式锁，确保同时只有一个下载任务运行
    使用阻塞等待模式，后续任务会排队等待
    """
    lock_acquired = False
    lock_value = f"{avid}:{os.getpid()}:{time.time()}"

    try:
        # 尝试获取锁，阻塞等待直到获取成功
        while not lock_acquired:
            # 使用 SET NX EX 原子操作
            lock_acquired = _redis_client.set(
                _DOWNLOAD_LOCK_KEY,
                lock_value,
                nx=True,  # 只在 key 不存在时设置
                ex=timeout  # 设置过期时间防止死锁
            )
            if not lock_acquired:
                # 获取当前持有锁的任务信息
                current_lock_info = _redis_client.get(_DOWNLOAD_LOCK_KEY)
                if current_lock_info:
                    logger.info(f"等待下载锁释放，当前锁持有者: {current_lock_info.decode()}")
                time.sleep(5)  # 等待 5 秒后重试

        logger.info(f"获取下载锁成功: {avid}")
        yield

    finally:
        if lock_acquired:
            # 只释放自己持有的锁
            current_value = _redis_client.get(_DOWNLOAD_LOCK_KEY)
            if current_value and current_value.decode() == lock_value:
                _redis_client.delete(_DOWNLOAD_LOCK_KEY)
                logger.info(f"释放下载锁: {avid}")


def check_task_in_queue(avid: str) -> bool:
    """
    检查指定avid的任务是否已在队列中

    Args:
        avid: 视频编号

    Returns:
        bool: True表示任务已在队列中，False表示可以添加新任务
    """
    task_key = _TASK_QUEUE_KEY.format(avid=avid.upper())
    return _redis_client.exists(task_key)


@contextmanager
def redis_task_queue_lock(avid: str, timeout: int = _TASK_QUEUE_TIMEOUT):
    """
    Redis 任务队列锁，防止同一avid重复提交任务

    Args:
        avid: 视频编号
        timeout: 锁超时时间

    Yields:
        bool: True表示成功获取锁（可以提交任务），False表示任务已存在
    """
    avid = avid.upper()
    task_key = _TASK_QUEUE_KEY.format(avid=avid)
    lock_value = f"{avid}:{os.getpid()}:{time.time()}"

    # 尝试设置任务队列锁
    lock_acquired = _redis_client.set(
        task_key,
        lock_value,
        nx=True,  # 只在 key 不存在时设置
        ex=timeout  # 设置过期时间
    )

    try:
        yield lock_acquired
    finally:
        if lock_acquired:
            # 只释放自己持有的锁
            current_value = _redis_client.get(task_key)
            if current_value and current_value.decode() == lock_value:
                _redis_client.delete(task_key)



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
        with redis_download_lock(avid):
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
