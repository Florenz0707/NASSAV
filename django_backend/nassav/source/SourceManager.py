import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from asgiref.sync import sync_to_async
from django.conf import settings
from loguru import logger
from nassav.scraper import AVDownloadInfo, ScraperManager
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

        # 初始化元数据刮削器
        self.scraper = ScraperManager(proxy)

        # 注册下载器，根据配置中的权重
        source_config = settings.SOURCE_CONFIG

        for source_name, source_class in self.SOURCE_CLASSES.items():
            config = source_config.get(source_name, {})
            weight = config.get("weight")
            # 只有配置了有效权重的源才会被注册
            if weight:
                source = source_class(proxy)
                self.sources[source.get_source_name()] = source

        # 从数据库加载 cookie
        sync_to_async(self.load_cookies_from_db)

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
    ) -> Optional[Tuple[AVDownloadInfo, SourceBase, str]]:
        """
        遍历所有源获取信息
        返回: (info, source, html) 或 None
        """
        import time

        for name, source in self.get_sorted_sources():
            logger.info(f"尝试从 {name} 获取 {avid}")
            html = source.get_html(avid)
            time.sleep(0.5)
            if html:
                info = source.parse_html(html)
                if info:
                    info.avid = avid.upper()
                    return info, source, html
        return None

    def get_info_from_source(
        self, avid: str, source_str: str
    ) -> Optional[Tuple[AVDownloadInfo, SourceBase, str]]:
        """
        从指定源获取信息
        返回: (info, source, html) 或 None
        """
        # 查找对应的下载器（不区分大小写）
        source = None
        for name, dl in self.sources.items():
            if name.lower() == source_str.lower():
                source = dl
                break

        if not source:
            logger.warning(f"未找到源 {source_str} 对应的下载器")
            return None

        logger.info(f"从 {source_str} 刷新 {avid}")
        html = source.get_html(avid)
        if html:
            logger.info(f"成功从源 {source_str} 获取 html")
            info = source.parse_html(html)
            if info:
                info.avid = avid.upper()
                return info, source, html

        logger.warning(f"从 {source_str} 获取 {avid} 失败")
        return None

    def get_resource_dir(self, avid: str) -> Path:
        """确保新的资源子目录存在并返回资源根目录

        注意：新的布局将封面和视频分开保存在 COVER_DIR/VIDEO_DIR，
        该方法保持兼容性，确保相关目录存在。返回值为资源根目录。"""
        cover_dir = Path(settings.COVER_DIR)
        video_dir = Path(settings.VIDEO_DIR)
        cover_dir.mkdir(parents=True, exist_ok=True)
        video_dir.mkdir(parents=True, exist_ok=True)
        return Path(settings.RESOURCE_DIR)

    def save_all_resources(
        self, avid: str, info: AVDownloadInfo, source: SourceBase, html: str
    ) -> dict:
        """
        一次性保存所有资源到 resource/{avid}/ 目录
        包括: HTML缓存、封面、元数据
        返回保存状态
        """
        avid = avid.upper()
        resource_dir = self.get_resource_dir(avid)
        result = {
            "cover_saved": False,
            "metadata_saved": False,
            "scraped": False,
        }

        # NOTE: 不再将 HTML/JSON 持久化到磁盘，元数据将保存到数据库。

        # 2. 下载封面到新的 COVER_DIR
        cover_url = source.get_cover_url(html)
        if cover_url:
            logger.info(f"封面下载地址: {cover_url}")
            cover_path = Path(settings.COVER_DIR) / f"{avid}.jpg"
            if source.download_file(cover_url, str(cover_path)):
                result["cover_saved"] = True
            else:
                logger.warning(f"封面下载失败: {avid}")
        else:
            logger.warning(f"未找到封面URL: {avid}")

        # 3. 从 JavBus 刮削器获取完整元数据
        scraped_data = self.scraper.scrape(avid)
        if scraped_data:
            info.update_from_scraper(scraped_data)
            result["scraped"] = True
            logger.info(f"已从 JavBus 获取 {avid} 的完整元数据（标题、发行日期、时长、演员等）")
        else:
            logger.warning(f"未能从 JavBus 获取 {avid} 的元数据，将只保存 Source 提供的基本信息")

        # 4. 保存元数据到数据库（AVResource），不再保存为 JSON 文件
        try:
            from nassav.models import Actor, AVResource, Genre

            # 更新 info（scraper 已可能补充信息）
            source_name = ""
            try:
                source_name = source.get_source_name()
            except Exception:
                source_name = getattr(info, "source", "") or ""

            # 检查资源是否已存在，用于判断是新增还是刷新
            existing_resource = AVResource.objects.filter(avid=avid).first()

            # 规范化 source_title（确保以 AVID 开头）
            raw_source_title = getattr(info, "source_title", "") or ""
            normalized_source_title = (
                normalize_source_title(avid, raw_source_title)
                if raw_source_title
                else ""
            )

            defaults = {
                "title": getattr(info, "title", "") or "",  # Scraper 提供的规范标题（日语）
                "source_title": normalized_source_title,  # Source 提供的备用标题（已规范化）
                "source": source_name or getattr(info, "source", "") or "",
                "release_date": getattr(info, "release_date", "") or "",
                "duration": None,
                "metadata": None,
                "m3u8": getattr(info, "m3u8", "") or "",
                "cover_filename": None,
            }

            # 对于新资源，设置初始状态
            if not existing_resource:
                defaults["translation_status"] = "pending"
                defaults["file_exists"] = False
                defaults["file_size"] = None
            # 对于已有资源（刷新操作），保留文件相关字段和翻译状态
            else:
                # 保留文件状态（刷新不应改变文件是否存在）
                defaults["file_exists"] = existing_resource.file_exists
                defaults["file_size"] = existing_resource.file_size
                # 保留翻译相关字段（刷新不应重置翻译状态和译文）
                defaults["translation_status"] = existing_resource.translation_status
                defaults["translated_title"] = existing_resource.translated_title

            # 尝试解析 duration 为秒数（若可用）
            try:
                if getattr(info, "duration", None):
                    # 解析类似 '120分' 或 '120' 等格式为秒
                    import re

                    m = re.search(r"(\d+)", str(info.duration))
                    if m:
                        mins = int(m.group(1))
                        defaults["duration"] = mins * 60
            except Exception:
                pass

            # 保存/更新资源基础记录
            resource_obj, created = AVResource.objects.update_or_create(
                avid=avid, defaults=defaults
            )

            # actors
            try:
                resource_obj.actors.clear()
                for actor_name in getattr(info, "actors", []) or []:
                    if not actor_name:
                        continue
                    actor_obj, _ = Actor.objects.get_or_create(name=actor_name)
                    resource_obj.actors.add(actor_obj)
            except Exception:
                logger.exception(f"保存 actors 失败: {avid}")

            # genres
            try:
                resource_obj.genres.clear()
                for genre_name in getattr(info, "genres", []) or []:
                    if not genre_name:
                        continue
                    genre_obj, _ = Genre.objects.get_or_create(name=genre_name)
                    resource_obj.genres.add(genre_obj)
            except Exception:
                logger.exception(f"保存 genres 失败: {avid}")

            # 封面文件名写入（如果刚下载成功）
            try:
                if result["cover_saved"]:
                    cover_path = Path(settings.COVER_DIR) / f"{avid}.jpg"
                    if cover_path.exists():
                        resource_obj.cover_filename = cover_path.name
                        # 生成缩略图（small/medium/large）到 COVER_DIR/thumbnails/{size}/{AVID}.jpg
                        try:
                            from nassav import utils as nassav_utils

                            sizes = {"small": 200, "medium": 600, "large": 1200}
                            for _name, _width in sizes.items():
                                dest = (
                                    Path(settings.COVER_DIR)
                                    / "thumbnails"
                                    / _name
                                    / f"{avid}.jpg"
                                )
                                nassav_utils.generate_thumbnail(
                                    cover_path, dest, _width
                                )
                        except Exception:
                            logger.exception(f"生成缩略图失败: {avid}")
                resource_obj.metadata = (
                    info.__dict__ if hasattr(info, "__dict__") else None
                )
                resource_obj.m3u8 = getattr(info, "m3u8", "") or ""
                resource_obj.save()
                result["metadata_saved"] = True

                # 5. 提交异步翻译任务（Celery）
                result["translate_task_submitted"] = False
                title_to_translate = resource_obj.title or resource_obj.source_title
                if title_to_translate and not resource_obj.translated_title:
                    try:
                        from nassav.tasks import submit_translate_task

                        task_result, is_async = submit_translate_task(
                            avid, async_mode=True
                        )
                        result["translate_task_submitted"] = True
                        if is_async:
                            result["translate_task_id"] = task_result.id
                            logger.info(f"已提交异步翻译任务: {avid}")
                        else:
                            # 同步执行的结果
                            result["translated"] = task_result.get("success", False)
                            logger.info(f"同步翻译完成: {avid}")
                    except Exception as e:
                        logger.warning(f"提交翻译任务失败: {avid}, 错误: {e}")
                elif resource_obj.translated_title:
                    logger.debug(f"跳过翻译（已有译文）: {avid}")
                    result["translated"] = True
                else:
                    logger.debug(f"跳过翻译（无标题）: {avid}")

            except Exception as e:
                logger.error(f"写入数据库元数据失败: {e}")
                result["metadata_saved"] = False

        except Exception as e:
            logger.error(f"保存元数据到数据库失败: {e}")
            result["metadata_saved"] = False

        return result

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

    def load_cached_metadata(self, avid: str) -> Optional[AVDownloadInfo]:
        """从缓存加载元数据"""
        avid = avid.upper()
        # 优先从数据库加载元数据（不再依赖 resource/*/*.json 文件）
        try:
            from nassav.models import AVResource

            resource = AVResource.objects.filter(avid=avid).first()
            if not resource:
                return None

            info = AVDownloadInfo(
                m3u8=resource.m3u8 or "",
                title=resource.title or "",
                avid=resource.avid or "",
                source=resource.source or "",
            )

            # 从 metadata JSON 字段恢复 actors/genres/release_date/duration 等（若存在）
            try:
                md = resource.metadata or {}
                if isinstance(md, dict):
                    info.release_date = md.get(
                        "release_date", resource.release_date or ""
                    )
                    info.duration = md.get("duration", resource.duration or "")
                    info.actors = md.get("actors", []) or []
                    info.genres = md.get("genres", []) or []
            except Exception:
                pass

            return info
        except Exception as e:
            logger.error(f"从数据库加载元数据失败: {e}")
            return None


source_manager = SourceManager()
