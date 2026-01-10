"""
ResourceService - 资源服务层
负责组合各个Manager完成完整的资源操作流程

职责:
1. 组合 SourceManager, ScraperManager, M3u8Downloader, TranslatorManager
2. 处理数据库操作 (AVResource, Actor, Genre)
3. 处理文件操作 (封面、头像、缩略图、HTML)
4. 编排业务流程 (获取源信息 -> 刮削元数据 -> 保存数据库 -> 提交翻译任务)
"""
import json
import os
from pathlib import Path
from typing import Optional, Tuple

from django.conf import settings
from django.utils import timezone
from loguru import logger
from nassav.models import Actor, AVResource, Genre
from nassav.scraper import AVDownloadInfo
from nassav.scraper.ScraperManager import ScraperManager
from nassav.source.SourceBase import SourceBase
from nassav.source.SourceManager import SourceManager
from nassav.translator.TranslatorManager import TranslatorManager

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 自定义异常
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class ResourceServiceException(Exception):
    """ResourceService 基础异常"""

    pass


class ResourceAlreadyExistsError(ResourceServiceException):
    """资源已存在异常 (409 Conflict)"""

    def __init__(self, avid: str, resource_data: dict):
        self.avid = avid
        self.resource_data = resource_data
        super().__init__(f"资源 {avid} 已存在")


class ResourceNotFoundError(ResourceServiceException):
    """资源未找到异常 (404 Not Found)"""

    def __init__(self, avid: str, errors: dict):
        self.avid = avid
        self.errors = errors
        super().__init__(
            f"获取{avid}失败。{', '.join(f'{k}:{v}' for k, v in errors.items())}"
        )


class ResourceAccessDeniedError(ResourceServiceException):
    """资源访问被拒绝异常 (403 Forbidden)"""

    def __init__(self, avid: str, errors: dict):
        self.avid = avid
        self.errors = errors
        super().__init__(
            f"访问{avid}被拒绝。{', '.join(f'{k}:{v}' for k, v in errors.items())}"
        )


class ResourceFetchError(ResourceServiceException):
    """资源获取失败异常 (502 Bad Gateway)"""

    def __init__(self, avid: str, errors: dict):
        self.avid = avid
        self.errors = errors
        super().__init__(
            f"获取{avid}失败。{', '.join(f'{k}:{v}' for k, v in errors.items())}"
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ResourceService 核心类
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class ResourceService:
    """
    资源服务 - 组合各个Manager完成完整的资源操作

    设计原则:
    - 依赖注入: 所有Manager通过构造函数注入,便于测试
    - 单一职责: 专注于资源操作流程编排,不直接处理HTTP请求
    - 错误传播: 使用自定义异常向上传播错误信息
    """

    def __init__(
        self,
        source_manager: SourceManager,
        scraper_manager: ScraperManager,
        translator_manager: TranslatorManager,
    ):
        """
        初始化资源服务

        Args:
            source_manager: 下载源管理器
            scraper_manager: 刮削器管理器
            translator_manager: 翻译器管理器
        """
        self.source_manager = source_manager
        self.scraper_manager = scraper_manager
        self.translator_manager = translator_manager

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 公共方法
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def add_resource(
        self,
        avid: str,
        source: str = "any",
        *,
        scrape: bool = True,
        download_cover: bool = True,
        submit_translate: bool = True,
    ) -> dict:
        """
        添加新资源（完整流程）

        Args:
            avid: 视频编号
            source: 指定源或 "any"
            scrape: 是否刮削 Javbus 元数据
            download_cover: 是否下载封面
            submit_translate: 是否提交翻译任务

        Returns:
            {
                "resource": AVResource对象,
                "cover_saved": bool,
                "metadata_saved": bool,
                "scraped": bool,
                "translate_task_id": str (可选)
            }

        Raises:
            ResourceAlreadyExistsError: 资源已存在
            ResourceNotFoundError: 所有源都返回404
            ResourceAccessDeniedError: 有源返回403
            ResourceFetchError: 网络错误
        """
        avid = avid.upper()
        logger.info(f"[ResourceService] 开始添加资源: {avid}, source={source}")

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # Step 1: 检查资源是否已存在
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        existing = AVResource.objects.filter(avid=avid).first()
        if existing:
            logger.warning(f"资源 {avid} 已存在")
            raise ResourceAlreadyExistsError(
                avid, self._serialize_resource(existing, include_relations=True)
            )

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # Step 2: 从源获取资源信息
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        info, source_inst, html, errors = self._get_source_info(avid, source)

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # Step 3: 保存所有资源
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        result = self._save_all_resources(
            avid,
            info,
            source_inst,
            html,
            scrape=scrape,
            download_cover=download_cover,
            submit_translate=submit_translate,
        )

        logger.info(f"[ResourceService] 资源 {avid} 添加成功")
        return result

    def refresh_resource(
        self, avid: str, *, scrape: bool = True, download_cover: bool = True
    ) -> dict:
        """
        刷新已有资源的元数据和m3u8链接

        Args:
            avid: 视频编号
            scrape: 是否刮削 Javbus 元数据
            download_cover: 是否下载封面

        Returns:
            {
                "resource": AVResource对象,
                "cover_saved": bool,
                "metadata_saved": bool,
                "scraped": bool,
                "m3u8_updated": bool
            }

        Raises:
            ResourceNotFoundError: 数据库中不存在该资源
        """
        avid = avid.upper()
        logger.info(f"[ResourceService] 开始刷新资源: {avid}")

        # 检查资源是否存在
        resource = AVResource.objects.filter(avid=avid).first()
        if not resource:
            logger.error(f"资源 {avid} 不存在于数据库中")
            raise ResourceNotFoundError(avid, {"database": "404"})

        # 从源获取最新信息
        source_name = resource.source
        info, source_inst, html, errors = self._get_source_info(avid, source_name)

        # 更新资源
        result = self._save_all_resources(
            avid,
            info,
            source_inst,
            html,
            scrape=scrape,
            download_cover=download_cover,
            submit_translate=False,  # 刷新时不提交翻译任务
        )

        result["m3u8_updated"] = True
        logger.info(f"[ResourceService] 资源 {avid} 刷新成功")
        return result

    def delete_resource(self, avid: str, *, delete_files: bool = False) -> bool:
        """
        删除资源

        Args:
            avid: 视频编号
            delete_files: 是否同时删除文件（封面、视频等）

        Returns:
            是否删除成功
        """
        avid = avid.upper()
        logger.info(f"[ResourceService] 开始删除资源: {avid}, delete_files={delete_files}")

        resource = AVResource.objects.filter(avid=avid).first()
        if not resource:
            logger.warning(f"资源 {avid} 不存在")
            return False

        # 删除文件
        if delete_files:
            self._delete_resource_files(avid)

        # 删除数据库记录
        resource.delete()
        logger.info(f"[ResourceService] 资源 {avid} 删除成功")
        return True

    def get_resource(self, avid: str) -> Optional[dict]:
        """
        获取资源信息

        Args:
            avid: 视频编号

        Returns:
            资源字典,如果不存在则返回None
        """
        avid = avid.upper()
        resource = AVResource.objects.filter(avid=avid).first()
        if not resource:
            return None
        return self._serialize_resource(resource, include_relations=True)

    def load_cached_metadata(self, avid: str) -> Optional[AVDownloadInfo]:
        """
        从数据库加载缓存的元数据

        Args:
            avid: 视频编号

        Returns:
            AVDownloadInfo对象,如果不存在则返回None
        """
        avid = avid.upper()
        resource = AVResource.objects.filter(avid=avid).first()
        if not resource:
            return None

        # 从metadata字段恢复AVDownloadInfo
        metadata = resource.metadata or {}

        if not metadata:
            return None

        return AVDownloadInfo(
            avid=metadata.get("avid", avid),
            source_title=metadata.get("source_title", ""),
            m3u8=metadata.get("m3u8", ""),
            duration=metadata.get("duration", ""),
            source=resource.source,
            # 如果有scraper数据，也恢复title字段
            title=metadata.get("title", ""),
        )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 私有方法 - 业务流程
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _get_source_info(
        self, avid: str, source: str
    ) -> Tuple[AVDownloadInfo, SourceBase, str, dict]:
        """
        从源获取资源信息

        Returns:
            (info, source_inst, html, errors)

        Raises:
            ResourceNotFoundError: 所有源都返回404
            ResourceAccessDeniedError: 有源返回403
            ResourceFetchError: 其他错误
        """
        if source == "any":
            (
                info,
                source_inst,
                html,
                errors,
            ) = self.source_manager.get_info_from_any_source(avid)
        else:
            info, source_inst, html, errors = self.source_manager.get_info_from_source(
                avid, source
            )

        # 错误处理
        if not info:
            has_403 = any(int(v) == 403 for v in errors.values() if v)
            all_404 = all(int(v) == 404 for v in errors.values() if v)

            if has_403:
                raise ResourceAccessDeniedError(avid, errors)
            elif all_404:
                raise ResourceNotFoundError(avid, errors)
            else:
                raise ResourceFetchError(avid, errors)

        return info, source_inst, html, errors

    def _save_all_resources(
        self,
        avid: str,
        info: AVDownloadInfo,
        source_inst: SourceBase,
        html: str,
        *,
        scrape: bool = True,
        download_cover: bool = True,
        submit_translate: bool = True,
    ) -> dict:
        """
        保存所有资源（从 SourceManager.save_all_resources 迁移）

        Returns:
            {
                "resource": AVResource对象,
                "cover_saved": bool,
                "metadata_saved": bool,
                "scraped": bool,
                "translate_task_id": str (可选)
            }
        """
        logger.info(f"[ResourceService] 开始保存资源: {avid}")

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # Step 1: 保存HTML原始页面
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        html_path = Path(settings.COVER_DIR) / f"{avid}.html"
        html_path.parent.mkdir(parents=True, exist_ok=True)
        html_path.write_text(html, encoding="utf-8")

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # Step 2: 刮削Javbus元数据（可选）
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        scraped_data = None
        if scrape:
            scraped_data = self._scrape_metadata(avid)

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # Step 3: 下载封面图片（可选）
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        cover_saved = False
        if download_cover:
            cover_saved = self._download_cover(avid, scraped_data, source_inst, html)

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # Step 4: 保存到数据库
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        resource = self._save_to_database(avid, info, source_inst, scraped_data)

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # Step 5: 下载演员头像（可选）
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        if scrape and scraped_data:
            self._download_avatars(scraped_data)

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # Step 6: 提交翻译任务（可选）
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        translate_task_id = None
        if submit_translate and scraped_data:
            translate_task_id = self._submit_translate_task(avid)

        # 构造返回结果
        result = {
            "resource": self._serialize_resource(resource, include_relations=True),
            "cover_saved": cover_saved,
            "metadata_saved": True,
            "scraped": scraped_data is not None,
        }

        if translate_task_id:
            result["translate_task_id"] = translate_task_id

        logger.info(f"[ResourceService] 资源 {avid} 保存完成")
        return result

    def _scrape_metadata(self, avid: str) -> Optional[dict]:
        """
        刮削Javbus元数据

        Returns:
            {
                "original_title": str,
                "release_date": str,
                "duration": int,
                "actors": [{"name": str, "avatar_url": str}],
                "genres": [str],
                "cover_url": str
            }
        """
        logger.info(f"[ResourceService] 开始刮削元数据: {avid}")
        scraped_data = self.scraper_manager.scrape(avid)

        if scraped_data:
            logger.info(f"[ResourceService] 刮削成功: {avid}")
        else:
            logger.warning(f"[ResourceService] 刮削失败: {avid}")

        return scraped_data

    def _download_cover(
        self,
        avid: str,
        scraped_data: Optional[dict],
        source_inst: SourceBase,
        html: str,
    ) -> bool:
        """
        下载封面图片（双源备份策略）

        优先级:
        1. Javbus封面 (scraped_data.cover_url)
        2. 源网站封面 (source_inst.get_cover_url())

        Returns:
            是否下载成功
        """
        logger.info(f"[ResourceService] 开始下载封面: {avid}")

        cover_path = Path(settings.COVER_DIR) / f"{avid}.jpg"
        cover_path.parent.mkdir(parents=True, exist_ok=True)

        # 策略1: 尝试Javbus封面
        if scraped_data and scraped_data.get("cover_url"):
            cover_url = scraped_data["cover_url"]
            if self.scraper_manager.download_cover(cover_url, str(cover_path)):
                logger.info(f"[ResourceService] 从Javbus下载封面成功: {avid}")
                return True

        # 策略2: 尝试源网站封面
        cover_url = source_inst.get_cover_url(html)
        if cover_url:
            source_name = source_inst.get_source_name()
            if source_inst.download_file(cover_url, str(cover_path)):
                logger.info(f"[ResourceService] 从{source_name}下载封面成功: {avid}")
                return True

        logger.warning(f"[ResourceService] 封面下载失败: {avid}")
        return False

    def _save_to_database(
        self,
        avid: str,
        info: AVDownloadInfo,
        source_inst: SourceBase,
        scraped_data: Optional[dict],
    ) -> AVResource:
        """
        保存资源到数据库（创建或更新）

        Returns:
            AVResource对象
        """
        from nassav.source.SourceManager import normalize_source_title

        logger.info(f"[ResourceService] 开始保存数据库记录: {avid}")

        # 获取源名称
        source_name = source_inst.get_source_name()

        # 规范化source_title，确保以AVID开头
        # 注意：使用info.source_title而不是info.title，因为source_title是从Source获取的
        normalized_source_title = normalize_source_title(avid, info.source_title)

        # 准备数据
        defaults = {
            "source_title": normalized_source_title,
            "source": source_name,
            "m3u8": info.m3u8,
            "cover_filename": f"{avid}.jpg",
            "translation_status": "pending",
        }

        # 如果有刮削数据，更新AVDownloadInfo对象并保存完整metadata
        if scraped_data:
            # 更新info对象（与旧代码保持一致）
            info.update_from_scraper(scraped_data)

            # 保存完整的AVDownloadInfo对象到metadata（与旧代码保持一致）
            defaults["metadata"] = info.__dict__ if hasattr(info, "__dict__") else None

            # 从scraper获取的标题字段是"title"，映射到数据库的original_title
            defaults["original_title"] = scraped_data.get("title", "")
            defaults["release_date"] = scraped_data.get("release_date", "")

            # 解析duration (可能是"98分钟"这样的字符串)
            duration_value = scraped_data.get("duration", 0)
            defaults["duration"] = self._parse_duration(duration_value)
        else:
            # 没有刮削数据时，保存基本的source信息
            defaults["metadata"] = {
                "m3u8": info.m3u8,
                "source_title": normalized_source_title,
                "avid": avid,
                "source": source_name,
            }

        # 创建或更新资源
        resource, created = AVResource.objects.update_or_create(
            avid=avid, defaults=defaults
        )

        action = "创建" if created else "更新"
        logger.info(f"[ResourceService] 数据库记录{action}成功: {avid}")

        # 关联演员和类别（如果有刮削数据）
        if scraped_data:
            self._associate_actors(resource, scraped_data.get("actors", []))
            self._associate_genres(resource, scraped_data.get("genres", []))

        return resource

    def _associate_actors(self, resource: AVResource, actors: list):
        """关联演员"""
        if not actors:
            return

        for actor_data in actors:
            actor_name = (
                actor_data.get("name") if isinstance(actor_data, dict) else actor_data
            )
            if actor_name:
                actor, _ = Actor.objects.get_or_create(name=actor_name)
                resource.actors.add(actor)

    def _associate_genres(self, resource: AVResource, genres: list):
        """关联类别"""
        if not genres:
            return

        for genre_name in genres:
            if genre_name:
                genre, _ = Genre.objects.get_or_create(name=genre_name)
                resource.genres.add(genre)

    def _download_avatars(self, scraped_data: dict):
        """
        下载演员头像

        Args:
            scraped_data: 刮削数据（包含actors列表）
        """
        actors = scraped_data.get("actors", [])
        if not actors:
            return

        logger.info(f"[ResourceService] 开始下载演员头像: {len(actors)} 个")

        for actor_data in actors:
            if not isinstance(actor_data, dict):
                continue

            actor_name = actor_data.get("name")
            avatar_url = actor_data.get("avatar_url")

            if not actor_name or not avatar_url:
                continue

            # 下载头像
            avatar_path = Path(settings.AVATAR_DIR) / f"{actor_name}.jpg"
            avatar_path.parent.mkdir(parents=True, exist_ok=True)

            try:
                # 获取第一个可用的scraper来下载头像
                scrapers = self.scraper_manager.get_scrapers()
                if scrapers:
                    _, scraper_instance = scrapers[0]
                    if scraper_instance.download_avatar(avatar_url, str(avatar_path)):
                        logger.info(f"演员头像下载成功: {actor_name}")
                    else:
                        logger.warning(f"演员头像下载失败: {actor_name}")
                else:
                    logger.warning("没有可用的刮削器来下载头像")
            except Exception as e:
                logger.error(f"演员头像下载异常: {actor_name}, {e}")

    def _submit_translate_task(self, avid: str) -> Optional[str]:
        """
        提交翻译任务

        Returns:
            任务ID（如果成功）
        """
        logger.info(f"[ResourceService] 提交翻译任务: {avid}")

        try:
            # 导入Celery任务
            from nassav.tasks import translate_title_task

            # 提交异步任务
            task = translate_title_task.delay(avid)
            logger.info(f"[ResourceService] 翻译任务已提交: {avid}, task_id={task.id}")
            return task.id
        except Exception as e:
            logger.error(f"[ResourceService] 提交翻译任务失败: {avid}, {e}")
            return None

    def _delete_resource_files(self, avid: str):
        """
        删除资源相关的所有文件

        Args:
            avid: 视频编号
        """
        logger.info(f"[ResourceService] 开始删除资源文件: {avid}")

        files_to_delete = [
            Path(settings.COVER_DIR) / f"{avid}.jpg",  # 封面
            Path(settings.COVER_DIR) / f"{avid}.html",  # HTML
            Path(settings.VIDEO_DIR) / f"{avid}.mp4",  # 视频
        ]

        for file_path in files_to_delete:
            if file_path.exists():
                try:
                    file_path.unlink()
                    logger.info(f"文件已删除: {file_path}")
                except Exception as e:
                    logger.error(f"删除文件失败: {file_path}, {e}")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 私有方法 - 辅助函数
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _parse_duration(self, duration_value) -> int:
        """
        解析时长为秒数

        Args:
            duration_value: 时长值，可能是：
                - 整数（秒数）
                - "98分钟"
                - "120分"
                - None

        Returns:
            时长（秒），解析失败返回0
        """
        import re

        if duration_value is None:
            return 0

        # 如果已经是整数，直接返回
        if isinstance(duration_value, int):
            return duration_value

        # 如果是字符串，尝试解析
        if isinstance(duration_value, str):
            # 尝试匹配 "120分钟" 或 "120分" 格式
            match = re.search(r"(\d+)\s*分", duration_value)
            if match:
                minutes = int(match.group(1))
                return minutes * 60

            # 尝试直接转换为整数
            try:
                return int(duration_value)
            except ValueError:
                logger.warning(f"无法解析duration: {duration_value}")
                return 0

        # 其他类型，返回0
        logger.warning(f"未知的duration类型: {type(duration_value)}, value={duration_value}")
        return 0

    def _serialize_resource(
        self, resource: AVResource, include_relations: bool = False
    ) -> dict:
        """
        序列化资源对象

        Args:
            resource: AVResource对象
            include_relations: 是否包含关系字段（actors, genres）

        Returns:
            资源字典
        """
        data = {
            "avid": resource.avid,
            "original_title": resource.original_title,
            "source_title": resource.source_title,
            "translated_title": resource.translated_title,
            "translation_status": resource.translation_status,
            "source": resource.source,
            "release_date": resource.release_date,
            "duration": resource.duration,
            "m3u8": resource.m3u8,
            "cover_filename": resource.cover_filename,
            "file_exists": resource.file_exists,
            "file_size": resource.file_size,
            "metadata_created_at": (
                resource.metadata_created_at.isoformat()
                if resource.metadata_created_at
                else None
            ),
            "metadata_updated_at": (
                resource.metadata_updated_at.isoformat()
                if resource.metadata_updated_at
                else None
            ),
            "video_saved_at": (
                resource.video_saved_at.isoformat() if resource.video_saved_at else None
            ),
            "created_at": (
                resource.created_at.isoformat() if resource.created_at else None
            ),
        }

        if include_relations:
            data["actors"] = [actor.name for actor in resource.actors.all()]
            data["genres"] = [genre.name for genre in resource.genres.all()]

        return data


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 模块级单例
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# 导入依赖的Manager单例
from nassav.scraper.ScraperManager import scraper_manager
from nassav.source.SourceManager import source_manager
from nassav.translator.TranslatorManager import translator_manager

# 创建ResourceService单例
resource_service = ResourceService(
    source_manager=source_manager,
    scraper_manager=scraper_manager,
    translator_manager=translator_manager,
)

logger.info("[ResourceService] 模块级单例已创建")
