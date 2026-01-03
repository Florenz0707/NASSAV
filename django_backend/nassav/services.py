"""
服务层：封装下载器和刮削器逻辑
"""
from pathlib import Path
from typing import Optional

from django.conf import settings
from django.core.paginator import Paginator
from django.db.models import Q
from loguru import logger

# 初始化日志
LOG_DIR = settings.LOG_DIR
logger.add(
    str(LOG_DIR / "{time:YYYY-MM-DD}.log"),
    rotation="00:00",
    retention="7 days",
    enqueue=False,
    level="DEBUG",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
)

# 导入常量（为了向后兼容，重新导出HEADERS）
from nassav.constants import HEADERS
from nassav.m3u8downloader import M3u8DownloaderBase, N_m3u8DL_RE
from nassav.source.SourceManager import SourceManager, source_manager


class VideoDownloadService:
    """视频下载服务"""

    def __init__(
        self, resource_manager: SourceManager, m3u8_downloader: M3u8DownloaderBase
    ):
        """
        初始化视频下载服务

        Args:
            resource_manager: 资源管理器（获取元数据、封面等）
            m3u8_downloader: M3U8 下载器（下载视频流）
        """
        self.manager = resource_manager
        self.m3u8_downloader = m3u8_downloader

    def download_video(
        self, avid: str, progress_callback: Optional[callable] = None
    ) -> bool:
        """
        下载视频
        优先从缓存的元数据读取 m3u8 URL，避免重复 fetch_html

        Args:
            avid: 视频编号
            progress_callback: 进度回调函数
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
        duration_seconds = (
            self._parse_duration(info.duration) if info.duration else None
        )

        # 下载m3u8视频（使用 Redis 分布式锁确保只有一个下载任务运行）
        result = self._download_m3u8(
            info.m3u8, avid, domain, duration_seconds, progress_callback
        )
        logger.info(f"[{avid}] 下载{'成功' if result else '失败'}")
        return result

    def _parse_duration(self, duration_str: str) -> Optional[int]:
        """解析时长字符串，返回秒数"""
        import re

        if not duration_str:
            return None
        # 尝试匹配 "120分钟" 或 "120分" 格式
        match = re.search(r"(\d+)分", duration_str)
        if match:
            return int(match.group(1)) * 60
        # 尝试匹配纯数字
        match = re.search(r"(\d+)", duration_str)
        if match:
            return int(match.group(1)) * 60
        return None

    def _get_domain_from_source(self, source: str) -> str:
        """根据 downloader 名称获取对应的 domain"""
        source_lower = source.lower()
        source_config = settings.SOURCE_CONFIG.get(source_lower, {})
        return source_config.get("domain", source_lower + ".com")

    def _download_m3u8(
        self,
        url: str,
        avid: str,
        domain: str,
        total_duration: Optional[int] = None,
        progress_callback: Optional[callable] = None,
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
    ),
)


def list_resources(params):
    """Return (objects, pagination) for resources list based on params dict/querydict.

    Supported params: file_exists (true/false), source (comma separated), ordering,
    page, page_size.
    """
    qs = (
        source_manager.get_queryset()
        if hasattr(source_manager, "get_queryset")
        else None
    )
    # fallback to direct model import
    from nassav.models import AVResource

    if qs is None:
        qs = AVResource.objects.all()

    # support status: downloaded/pending/all (alias to file_exists)
    status = params.get("status")
    if status:
        s = str(status).lower()
        if s == "downloaded":
            qs = qs.filter(file_exists=True)
        elif s == "pending":
            qs = qs.filter(file_exists=False)

    # legacy/file_exists parameter (boolean-like)
    fe = params.get("file_exists")
    if fe is not None:
        if str(fe).lower() in ("1", "true", "yes"):
            qs = qs.filter(file_exists=True)
        else:
            qs = qs.filter(file_exists=False)

    source = params.get("source")
    if source:
        sources = [s.strip() for s in str(source).split(",") if s.strip()]
        qs = qs.filter(source__in=sources)

    # search parameter: match avid or title (case-insensitive contains)
    search = params.get("search")
    if search:
        q = str(search).strip()
        qs = qs.filter(Q(avid__icontains=q) | Q(title__icontains=q))

    # filter by actor (accept actor id or name fragment)
    actor = params.get("actor")
    if actor:
        try:
            aid = int(actor)
            qs = qs.filter(actors__id=aid)
        except Exception:
            a = str(actor).strip()
            if a:
                qs = qs.filter(actors__name__icontains=a)
        qs = qs.distinct()

    # filter by genre (accept genre id or name fragment)
    genre = params.get("genre")
    if genre:
        try:
            gid = int(genre)
            qs = qs.filter(genres__id=gid)
        except Exception:
            g = str(genre).strip()
            if g:
                qs = qs.filter(genres__name__icontains=g)
        qs = qs.distinct()

    ordering = params.get("ordering")
    if ordering:
        # 当按 video_saved_at 排序时，只返回已下载的视频
        # 避免返回 video_saved_at 为 NULL 的未下载资源
        if "video_saved_at" in ordering:
            qs = qs.filter(file_exists=True, video_saved_at__isnull=False)
        qs = qs.order_by(ordering)

    # pagination
    try:
        page = int(params.get("page", 1))
    except Exception:
        page = 1
    try:
        page_size = int(params.get("page_size", 20))
    except Exception:
        page_size = 20

    paginator = Paginator(qs, page_size)
    page_obj = paginator.get_page(page)

    return page_obj.object_list, {
        "total": paginator.count,
        "page": page_obj.number,
        "page_size": page_size,
        "pages": paginator.num_pages,
    }
