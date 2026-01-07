import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from asgiref.sync import sync_to_async
from django.conf import settings
from loguru import logger
from nassav.scraper import AVDownloadInfo
from nassav.source import Jable, Memo, MissAV, SourceBase


def normalize_source_title(avid: str, source_title: str) -> str:
    """规范化 source_title，确保以 AVID 开头

    Args:
        avid: 资源编号
        source_title: 原始标题

    Returns:
        规范化后的标题（以 AVID 开头）
    """
    if not source_title:
        return source_title

    avid_upper = avid.upper()
    # 检查标题是否已经以 AVID 开头（不区分大小写）
    if not source_title.upper().startswith(avid_upper):
        return f"{avid_upper} {source_title}"
    return source_title


class SourceManager:
    """下载器管理器"""

    # 下载器类映射
    SOURCE_CLASSES = {"missav": MissAV, "jable": Jable, "memo": Memo}

    def __init__(self):
        proxy = settings.PROXY_URL if settings.PROXY_ENABLED else None
        self.sources: Dict[str, SourceBase] = {}
        self._cookies_loaded = False

        # 注册下载器，根据配置中的权重
        source_config = settings.SOURCE_CONFIG

        for source_name, source_class in self.SOURCE_CLASSES.items():
            config = source_config.get(source_name, {})
            weight = config.get("weight")
            # 只有配置了有效权重的源才会被注册
            if weight:
                source = source_class(proxy)
                self.sources[source.get_source_name()] = source

        # Cookie 将在首次使用时懒加载

    def _ensure_cookies_loaded(self):
        """确保cookie已加载（懒加载）"""
        if not self._cookies_loaded:
            self.load_cookies_from_db()
            self._cookies_loaded = True

    def load_cookies_from_db(self):
        """从数据库加载所有源的 cookie"""
        try:
            from nassav.models import SourceCookie

            cookies = SourceCookie.objects.all()
            for cookie_obj in cookies:
                source_name = cookie_obj.source_name.lower()
                # 查找对应的源（不区分大小写）
                for name, source in self.sources.items():
                    if name.lower() == source_name:
                        source.set_cookie(cookie_obj.cookie)
                        logger.info(f"从数据库加载 {name} 的 Cookie")
                        break
        except Exception as e:
            logger.warning(f"从数据库加载 Cookie 失败: {e}")

    def set_source_cookie(self, source_name: str, cookie: str) -> bool:
        """
        设置指定源的 cookie，同时更新内存和数据库
        返回是否设置成功
        """
        # 查找对应的源（不区分大小写）
        target_source = None
        actual_name = None
        for name, source in self.sources.items():
            if name.lower() == source_name.lower():
                target_source = source
                actual_name = name
                break

        if not target_source:
            logger.warning(f"未找到源 {source_name}")
            return False

        # 更新内存中的 cookie
        target_source.set_cookie(cookie)
        logger.info(f"已设置 {actual_name} 的 Cookie")

        # 更新数据库
        try:
            from nassav.models import SourceCookie

            SourceCookie.objects.update_or_create(
                source_name=actual_name.lower(), defaults={"cookie": cookie}
            )
            return True
        except Exception as e:
            logger.error(f"保存 Cookie 到数据库失败: {e}")
            return False

    def get_sorted_sources(self) -> List[Tuple[str, SourceBase]]:
        """获取按权重排序的下载器列表"""
        source_config = settings.SOURCE_CONFIG
        sorted_items = []
        for name, downloader in self.sources.items():
            weight = source_config.get(name.lower(), {}).get("weight", 0)
            sorted_items.append((name, downloader, weight))
        sorted_items.sort(key=lambda x: x[2], reverse=True)
        return [(name, dl) for name, dl, _ in sorted_items]

    def get_info_from_any_source(
        self, avid: str
    ) -> Tuple[
        Optional[AVDownloadInfo], Optional[SourceBase], Optional[str], Dict[str, object]
    ]:
        """
        遍历所有源获取信息
        返回: (info, source, html, errors)
        errors: dict mapping source_name -> error_code (or error string)
        """
        import time

        self._ensure_cookies_loaded()

        errors: Dict[str, object] = {}

        for name, source in self.get_sorted_sources():
            logger.info(f"尝试从 {name} 获取 {avid}")
            # 重置源上的上次错误码
            try:
                source.last_error_code = None
            except Exception:
                pass

            html = source.get_html(avid)
            time.sleep(0.5)

            # 如果 fetch_html 记录了错误码且未获取到 html，则把错误码记录下来
            try:
                err = getattr(source, "last_error_code", None)
                if not html and err is not None:
                    errors[name] = err
            except Exception:
                pass

            if html:
                info = source.parse_html(html)
                if info:
                    info.avid = avid.upper()
                    return info, source, html, errors

        return None, None, None, errors

    def get_info_from_source(
        self, avid: str, source_str: str
    ) -> Tuple[
        Optional[AVDownloadInfo], Optional[SourceBase], Optional[str], Dict[str, object]
    ]:
        """
        从指定源获取信息
        返回: (info, source, html, errors)
        """
        self._ensure_cookies_loaded()

        errors: Dict[str, object] = {}

        # 查找对应的下载器（不区分大小写）
        source = None
        for name, dl in self.sources.items():
            if name.lower() == source_str.lower():
                source = dl
                break

        if not source:
            logger.warning(f"未找到源 {source_str} 对应的下载器")
            return None, None, None, errors

        logger.info(f"从 {source_str} 刷新 {avid}")
        try:
            source.last_error_code = None
        except Exception:
            pass

        html = source.get_html(avid)
        try:
            err = getattr(source, "last_error_code", None)
            if not html and err is not None:
                errors[source_str] = err
        except Exception:
            pass

        if html:
            logger.info(f"成功从源 {source_str} 获取 html")
            info = source.parse_html(html)
            if info:
                info.avid = avid.upper()
                return info, source, html, errors

        logger.warning(f"从 {source_str} 获取 {avid} 失败")
        return None, None, None, errors

    def get_resource_dir(self, avid: str) -> Path:
        """确保新的资源子目录存在并返回资源根目录

        注意：新的布局将封面和视频分开保存在 COVER_DIR/VIDEO_DIR，
        该方法保持兼容性，确保相关目录存在。返回值为资源根目录。"""
        cover_dir = Path(settings.COVER_DIR)
        video_dir = Path(settings.VIDEO_DIR)
        cover_dir.mkdir(parents=True, exist_ok=True)
        video_dir.mkdir(parents=True, exist_ok=True)
        return Path(settings.RESOURCE_DIR)

    def load_cached_html(self, avid: str) -> Optional[str]:
        """从缓存加载 HTML"""
        avid = avid.upper()
        # HTML 缓存如果存在于旧的 per-avid 目录（resource_backup/{avid}/{avid}.html），优先从备份目录读取
        html_path = Path(settings.RESOURCE_BACKUP_DIR) / avid / f"{avid}.html"
        if html_path.exists():
            try:
                with open(html_path, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception as e:
                logger.error(f"读取缓存 HTML 失败: {e}")
        return None


source_manager = SourceManager()
