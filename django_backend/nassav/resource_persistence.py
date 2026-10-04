"""Resource metadata persistence and actor/source relation synchronization."""

from abc import ABC, abstractmethod
from typing import Any
from copy import deepcopy
from dataclasses import dataclass

from django.utils import timezone
from loguru import logger

from nassav.models import AVResource, Actor, Genre
from nassav.scraper import AVDownloadInfo
from nassav.source.capabilities import SourceRelations
from nassav.source.jable_actor_mapping import (
    select_best_model_candidate,
    persist_actor_source_mapping,
)
from nassav.utils import parse_duration
from nassav.source.titles import normalize_source_title


@dataclass(frozen=True)
class ResourceSaveInput:
    avid: str
    info: AVDownloadInfo
    source_name: str
    scraped_data: dict | None = None
    relations: SourceRelations = SourceRelations()


class ResourcePersistence(ABC):
    """Write a resource and its metadata relations as one application operation."""

    @abstractmethod
    def save(self, data: ResourceSaveInput) -> AVResource:
        """Save parsed data without mutating its download info or scraper payload."""
        raise NotImplementedError


class DjangoResourcePersistence(ResourcePersistence):
    """Django ORM implementation of resource metadata persistence."""

    def save(self, data: ResourceSaveInput) -> AVResource:
        avid = data.avid
        info = deepcopy(data.info)
        scraped_data = data.scraped_data

        logger.info(f"[ResourceService] 开始保存数据库记录: {avid}")

        # 获取源名称
        source_name = data.source_name
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
        fallback_actor_names = list(data.relations.actor_names)
        if (
            scraped_data is not None
            and fallback_actor_names
            and not relation_payload.get("actors")
        ):
            scraped_payload["actors"] = fallback_actor_names
            relation_payload["actors"] = fallback_actor_names

        # 如果有刮削数据，更新AVDownloadInfo对象并保存完整metadata
        if scraped_payload:
            # 更新独立副本，避免污染来源缓存中的下载信息
            info.update_from_scraper(scraped_payload)

            # 保存完整的AVDownloadInfo对象到metadata（与旧代码保持一致）
            defaults["metadata"] = deepcopy(info.__dict__)

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
            self._sync_source_actor_mappings(resource, data.relations)

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

    def _sync_source_actor_mappings(
        self, resource: AVResource, relations: SourceRelations
    ) -> None:
        candidates = list(relations.actor_candidates)
        if not candidates:
            return
        for actor in resource.actors.all():
            selected, confidence, _ = select_best_model_candidate(
                actor_name=actor.name, candidates=candidates
            )
            if selected is not None:
                persist_actor_source_mapping(
                    actor=actor,
                    candidate=selected,
                    confidence=confidence,
                    match_method="imported",
                )
