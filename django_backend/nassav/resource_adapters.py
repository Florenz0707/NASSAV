"""Filesystem and queue/event adapters for resource workflows."""

from pathlib import Path

from django.conf import settings
from loguru import logger

from nassav.models import AVResource
from nassav.resource_contracts import (
    AssetResult,
    MetadataProvider,
    ResourceAssets,
    ResourceEvents,
    ResourceReader,
    TranslationSubmitter,
)
from nassav.signals import metadata_refreshed, resource_added
from nassav.source.SourceBase import SourceBase


class DjangoResourceReader(ResourceReader):
    def get(self, avid: str) -> AVResource | None:
        return AVResource.objects.filter(avid=avid).first()


class FileResourceAssets(ResourceAssets):
    def __init__(self, scraper_manager: MetadataProvider):
        self.scraper_manager = scraper_manager

    def save_page(self, avid: str, html: str) -> AssetResult:
        target = Path(settings.COVER_DIR) / f"{avid}.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(html, encoding="utf-8")
        return AssetResult(target, True)

    def save_cover(
        self,
        avid: str,
        scraped_data: dict | None,
        scraped_by: str | None,
        source_inst: SourceBase | None,
        html: str | None,
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
            if self.scraper_manager.download_cover(
                cover_url,
                str(cover_path),
                scraper_name=scraped_by,
            ):
                logger.info(f"[ResourceService] 从Javbus下载封面成功: {avid}")
                return True

        # 策略2: 尝试源网站封面
        if source_inst and html:
            cover_url = source_inst.get_cover_url(html)
            if cover_url:
                source_name = source_inst.get_source_name()
                if source_inst.download_file(cover_url, str(cover_path)):
                    logger.info(
                        f"[ResourceService] 从{source_name}下载封面成功: {avid}"
                    )
                    return True

        logger.warning(f"[ResourceService] 封面下载失败: {avid}")
        return False

    def save_avatars(self, scraped_data: dict):
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


class CeleryTranslationSubmitter(TranslationSubmitter):
    def submit(self, avid: str) -> str | None:
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


class SignalResourceEvents(ResourceEvents):
    def publish(self, event: str, sender: type, avid: str, result: dict) -> None:
        signal = resource_added if event == "added" else metadata_refreshed
        signal.send(
            sender=sender, avid=avid, resource=result.get("resource"), result=result
        )
