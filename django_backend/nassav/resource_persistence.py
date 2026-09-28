"""Resource metadata persistence and actor/source relation synchronization."""

from abc import ABC, abstractmethod
from typing import Any, Optional

from django.utils import timezone
from loguru import logger

from nassav.models import AVResource, Actor, Genre
from nassav.scraper import AVDownloadInfo
from nassav.source.SourceBase import SourceBase
from nassav.source.jable_actor_mapping import (
    parse_jable_model_candidates,
    sync_actor_source_mappings_from_jable_html,
)
from nassav.utils import parse_duration


class ResourcePersistence(ABC):
    """Write a resource and its metadata relations as one application operation."""

    @abstractmethod
    def save(
        self,
        avid: str,
        info: AVDownloadInfo,
        source_inst: SourceBase | None,
        scraped_data: Optional[dict],
        html: str | None = None,
    ) -> AVResource:
        """Create or update resource metadata and return its ORM record."""


class DjangoResourcePersistence(ResourcePersistence):
    """Django ORM implementation of resource metadata persistence."""

    def save(
        self,
        avid: str,
        info: AVDownloadInfo,
        source_inst: SourceBase | None,
        scraped_data: Optional[dict],
        html: str | None = None,
    ) -> AVResource:
        """
        保存资源到数据库（创建或更新）

        Returns:
            AVResource对象
        """
        from nassav.source.SourceManager import normalize_source_title

        logger.info(f"[ResourceService] 开始保存数据库记录: {avid}")

        # 获取源名称
        source_name = source_inst.get_source_name() if source_inst else "unknown"
        existing_resource = AVResource.objects.filter(avid=avid).first()

        # 规范化source_title，确保以AVID开头
        # 注意：使用info.source_title而不是info.title，因为source_title是从Source获取的
        normalized_source_title = normalize_source_title(avid, info.source_title)

        # 准备数据
        defaults: dict[str, Any] = {
            "source_title": normalized_source_title,
            "source": source_name,
            "m3u8": info.m3u8,
            "cover_filename": f"{avid}.jpg",
            "translation_status": "pending",
        }

        scraped_payload = dict(scraped_data or {})
        relation_payload = dict(scraped_payload)
        fallback_actor_names = self._extract_source_actor_names(source_inst, html)
        if (
            scraped_data is not None
            and fallback_actor_names
            and not relation_payload.get("actors")
        ):
            scraped_payload["actors"] = fallback_actor_names
            relation_payload["actors"] = fallback_actor_names

        # 如果有刮削数据，更新AVDownloadInfo对象并保存完整metadata
        if scraped_payload:
            # 更新info对象（与旧代码保持一致）
            info.update_from_scraper(scraped_payload)

            # 保存完整的AVDownloadInfo对象到metadata（与旧代码保持一致）
            defaults["metadata"] = info.__dict__

            # 从scraper获取的标题字段是"title"，映射到数据库的original_title
            defaults["original_title"] = scraped_payload.get("title", "")
            defaults["release_date"] = scraped_payload.get("release_date", "")

            # 解析duration (可能是"98分钟"这样的字符串)
            duration_value = scraped_payload.get("duration", 0)
            defaults["duration"] = parse_duration(duration_value)
        else:
            # 没有刮削数据时，保留已有metadata，仅更新source相关字段
            preserved_metadata = (
                dict(existing_resource.metadata or {}) if existing_resource else {}
            )
            preserved_metadata.update(
                {
                    "m3u8": info.m3u8,
                    "source_title": normalized_source_title,
                    "avid": avid,
                    "source": source_name,
                }
            )
            defaults["metadata"] = preserved_metadata

        # 创建或更新资源
        resource, created = AVResource.objects.update_or_create(
            avid=avid, defaults=defaults
        )

        if created:
            resource.metadata_created_at = timezone.now()
            resource.save(update_fields=["metadata_created_at"])

        action = "创建" if created else "更新"
        logger.info(f"[ResourceService] 数据库记录{action}成功: {avid}")

        # 关联演员和类别（如果有刮削数据）
        if relation_payload:
            self._associate_actors(resource, relation_payload.get("actors", []))
            self._associate_genres(resource, relation_payload.get("genres", []))
            self._sync_source_actor_mappings(resource, source_inst, html)

        return resource

    def _extract_source_actor_names(
        self,
        source_inst: SourceBase | None,
        html: str | None,
    ) -> list[str]:
        if not html:
            return []

        source_name = ""
        if source_inst is not None:
            source_name = str(source_inst.get_source_name() or "").strip().lower()
        if source_name != "jable":
            return []

        domain = getattr(source_inst, "domain", "jable.tv") or "jable.tv"
        candidates = parse_jable_model_candidates(
            html,
            base_url=f"https://{domain}/",
        )
        actor_names: list[str] = []
        seen_names: set[str] = set()
        for candidate in candidates:
            actor_name = str(candidate.source_actor_name or "").strip()
            if not actor_name or actor_name in seen_names:
                continue
            seen_names.add(actor_name)
            actor_names.append(actor_name)
        return actor_names

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

    def _sync_source_actor_mappings(
        self,
        resource: AVResource,
        source_inst: SourceBase | None,
        html: str | None,
    ) -> None:
        if not html:
            return

        source_name = ""
        if source_inst is not None:
            source_name = str(source_inst.get_source_name() or "").strip().lower()
        if not source_name:
            source_name = str(resource.source or "").strip().lower()
        if source_name != "jable":
            return

        actors = list(resource.actors.all())
        if not actors:
            return

        domain = getattr(source_inst, "domain", "jable.tv") or "jable.tv"
        stats = sync_actor_source_mappings_from_jable_html(
            actors=actors,
            html=html,
            base_url=f"https://{domain}/",
            match_method="imported",
        )
        if any(
            int(stats.get(key, 0)) > 0 for key in ("saved", "unmatched", "conflict")
        ):
            logger.info(
                "[ResourceService] Jable 演员映射同步完成: "
                f"saved={stats.get('saved', 0)}, "
                f"unmatched={stats.get('unmatched', 0)}, "
                f"conflict={stats.get('conflict', 0)}"
            )
