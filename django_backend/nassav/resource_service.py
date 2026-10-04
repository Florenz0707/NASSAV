"""
ResourceService - 资源服务层
负责组合各个Manager完成完整的资源操作流程

职责: 编排来源、元数据、资产、持久化、翻译提交与事件；具体副作用通过能力依赖注入。
"""

import traceback as tb
from datetime import datetime
from typing import Callable, Dict, Optional, Tuple

from loguru import logger
from nassav.models import AVResource
from nassav.scraper import AVDownloadInfo
from nassav.resource_persistence import (
    DjangoResourcePersistence,
    ResourcePersistence,
    ResourceSaveInput,
)
from nassav.resource_presentation import serialize_resource
from nassav.resource_adapters import (
    ResourceReader,
    DjangoResourceReader,
    ResourceAssets,
    FileResourceAssets,
    TranslationSubmitter,
    CeleryTranslationSubmitter,
    ResourceEvents,
    SignalResourceEvents,
)
from nassav.source.capabilities import SourceRelations
from nassav.resource_contracts import SourceLookup, MetadataProvider, ResourceWorkflow
from nassav.source.SourceBase import SourceBase
from nassav.translator.TranslatorManager import TranslatorManager

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 自定义异常
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class ResourceServiceException(Exception):
    """ResourceService 基础异常

    增强功能：
    - 自动捕获 traceback 信息
    - 记录异常发生时间
    - 自动记录日志
    """

    def __init__(self, message: str, **kwargs):
        super().__init__(message)
        self.message = message
        self.timestamp = datetime.now()
        self.traceback_info = (
            tb.format_exc() if tb.format_exc() != "NoneType: None\n" else None
        )
        self.context = kwargs

        # 自动记录日志
        self._log_exception()

    def _log_exception(self):
        """记录异常日志"""
        log_msg = f"{self.__class__.__name__}: {self.message}"
        if self.context:
            log_msg += f" | Context: {self.context}"
        logger.error(log_msg)
        if self.traceback_info:
            logger.debug(f"Traceback: {self.traceback_info}")

    def to_dict(self) -> dict:
        """转换为字典格式，便于序列化"""
        return {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "context": self.context,
            "traceback": self.traceback_info,
        }


class ResourceAlreadyExistsError(ResourceServiceException):
    """资源已存在异常 (409 Conflict)"""

    def __init__(self, avid: str, resource_data: dict, **kwargs):
        self.avid = avid
        self.resource_data = resource_data
        super().__init__(
            f"资源 {avid} 已存在", avid=avid, resource_data=resource_data, **kwargs
        )


class ResourceNotFoundError(ResourceServiceException):
    """资源未找到异常 (404 Not Found)"""

    def __init__(self, avid: str, errors: dict, **kwargs):
        self.avid = avid
        self.errors = errors
        error_details = ", ".join(f"{k}:{v}" for k, v in errors.items())
        super().__init__(
            f"获取{avid}失败。{error_details}", avid=avid, errors=errors, **kwargs
        )


class ResourceAccessDeniedError(ResourceServiceException):
    """资源访问被拒绝异常 (403 Forbidden)"""

    def __init__(self, avid: str, errors: dict, **kwargs):
        self.avid = avid
        self.errors = errors
        error_details = ", ".join(f"{k}:{v}" for k, v in errors.items())
        super().__init__(
            f"访问{avid}被拒绝。{error_details}", avid=avid, errors=errors, **kwargs
        )


class ResourceFetchError(ResourceServiceException):
    """资源获取失败异常 (502 Bad Gateway)"""

    def __init__(self, avid: str, errors: dict, **kwargs):
        self.avid = avid
        self.errors = errors
        error_details = ", ".join(f"{k}:{v}" for k, v in errors.items())
        super().__init__(
            f"获取{avid}失败。{error_details}", avid=avid, errors=errors, **kwargs
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ResourceService 核心类
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class ResourceService(ResourceWorkflow):
    """
    资源服务 - 组合各个Manager完成完整的资源操作

    设计原则:
    - 依赖注入: 所有Manager通过构造函数注入,便于测试
    - 单一职责: 专注于资源操作流程编排,不直接处理HTTP请求
    - 错误传播: 使用自定义异常向上传播错误信息
    """

    def __init__(
        self,
        source_manager: SourceLookup,
        scraper_manager: MetadataProvider,
        translator_manager: TranslatorManager,
        persistence: ResourcePersistence | None = None,
        *,
        reader: ResourceReader | None = None,
        assets: ResourceAssets | None = None,
        translations: TranslationSubmitter | None = None,
        events: ResourceEvents | None = None,
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
        self.persistence = (
            persistence if persistence is not None else DjangoResourcePersistence()
        )
        self.reader = reader if reader is not None else DjangoResourceReader()
        self.assets = (
            assets if assets is not None else FileResourceAssets(scraper_manager)
        )
        self.translations = (
            translations if translations is not None else CeleryTranslationSubmitter()
        )
        self.events = events if events is not None else SignalResourceEvents()

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
        progress: Callable[[str], None] | None = None,
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
        existing = self.reader.get(avid)
        if existing:
            logger.warning(f"资源 {avid} 已存在")
            raise ResourceAlreadyExistsError(
                avid, self._serialize_resource(existing, include_relations=True)
            )

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # Step 2: 从源获取资源信息
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        if progress:
            progress("source_lookup")
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
            progress=progress,
        )

        logger.info(f"[ResourceService] 资源 {avid} 添加成功")

        # 发布资源添加事件
        self.events.publish("added", self.__class__, avid, result)

        return result

    def refresh_resource(
        self,
        avid: str,
        *,
        scrape: bool = True,
        download_cover: bool = True,
        progress: Callable[[str], None] | None = None,
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
        resource = self.reader.get(avid)
        if not resource:
            logger.error(f"资源 {avid} 不存在于数据库中")
            raise ResourceNotFoundError(avid, {"database": "404"})

        # 从源获取最新信息
        source_name = resource.source
        if progress:
            progress("source_lookup")
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
            progress=progress,
        )

        result["m3u8_updated"] = True
        logger.info(f"[ResourceService] 资源 {avid} 刷新成功")

        # 发布元数据刷新事件
        self.events.publish("refreshed", self.__class__, avid, result)

        return result

    def delete_resource(self, avid: str, *, delete_files: bool = False) -> bool:
        """Compatibility entry point for callers that expect a boolean result."""
        from nassav.resource_deletion import resource_deletion_service

        return resource_deletion_service.delete_resource(
            avid, include_files=delete_files
        ).found

    def load_cached_metadata(self, avid: str) -> Optional[AVDownloadInfo]:
        """
        从数据库加载缓存的元数据

        Args:
            avid: 视频编号

        Returns:
            AVDownloadInfo对象,如果不存在则返回None
        """
        avid = avid.upper()
        resource = self.reader.get(avid)
        if not resource:
            return None

        # 从metadata字段恢复AVDownloadInfo
        if not resource.metadata:
            return None
        metadata = resource.metadata

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
    ) -> Tuple[
        AVDownloadInfo, SourceBase | None, str | None, Dict[str, int | str | None]
    ]:
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
        source_inst: SourceBase | None,
        html: str | None,
        *,
        scrape: bool = True,
        download_cover: bool = True,
        submit_translate: bool = True,
        progress: Callable[[str], None] | None = None,
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
        if html:
            self.assets.save_page(avid, html)

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # Step 2: 刮削Javbus元数据（可选）
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        scraped_data = None
        scraped_by = None
        if scrape:
            if progress:
                progress("metadata")
            scraped_data, scraped_by = self._scrape_metadata(avid)

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # Step 3: 下载封面图片（可选）
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        cover_saved = False
        if download_cover:
            if progress:
                progress("cover")
            cover_saved = self._download_cover(
                avid,
                scraped_data,
                scraped_by,
                source_inst,
                html,
            )

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # Step 4: 保存到数据库
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        if progress:
            progress("saving")
        resource = self._save_to_database(
            avid,
            info,
            source_inst,
            scraped_data,
            html=html,
        )

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
            if progress:
                progress("translation_queued")
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

    def _scrape_metadata(self, avid: str) -> tuple[Optional[dict], Optional[str]]:
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
        scraped_data, scraper_name = self.scraper_manager.scrape_with_source(avid)

        if scraped_data:
            logger.info(f"[ResourceService] 刮削成功: {avid}")
        else:
            logger.warning(f"[ResourceService] 刮削失败: {avid}")

        return scraped_data, scraper_name

    def _download_cover(
        self,
        avid: str,
        scraped_data: Optional[dict],
        scraped_by: Optional[str],
        source_inst: SourceBase | None,
        html: str | None,
    ) -> bool:
        return self.assets.save_cover(avid, scraped_data, scraped_by, source_inst, html)

    def _save_to_database(
        self,
        avid: str,
        info: AVDownloadInfo,
        source_inst: SourceBase | None,
        scraped_data: Optional[dict],
        html: str | None = None,
    ) -> AVResource:
        """Retain the existing service entry point for metadata persistence."""
        relations = (
            source_inst.parse_relations(html)
            if source_inst is not None and html
            else SourceRelations()
        )
        return self.persistence.save(
            ResourceSaveInput(
                avid,
                info,
                source_inst.get_source_name() if source_inst else "unknown",
                scraped_data,
                relations,
            )
        )

    def _download_avatars(self, scraped_data: dict):
        self.assets.save_avatars(scraped_data)

    def _submit_translate_task(self, avid: str) -> Optional[str]:
        return self.translations.submit(avid)

    def _serialize_resource(
        self, resource: AVResource, include_relations: bool = False
    ) -> dict:
        return serialize_resource(resource, include_relations)


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
