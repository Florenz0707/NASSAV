from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Protocol, cast

from django.conf import settings
from django.core.cache import cache
from django.db.models import Count
from loguru import logger

from nassav.models import Actor, Genre
from nassav.recommendation.actor_source_mapping import actor_source_mapping_service
from nassav.recommendation.genre_source_mapping import genre_source_mapping_service
from nassav.services import source_manager


@dataclass
class ExternalSearchResult:
    items: list[dict]
    pagination: dict[str, int]
    meta: dict[str, Any]


class ExternalSearchCacheBackend(ABC):
    @abstractmethod
    def get(self, key: str) -> list[dict] | None:
        raise NotImplementedError

    @abstractmethod
    def set(self, key: str, payload: list[dict], ttl_seconds: int) -> None:
        raise NotImplementedError


class NoopExternalSearchCacheBackend(ExternalSearchCacheBackend):
    def get(self, key: str) -> list[dict] | None:
        _ = key
        return None

    def set(self, key: str, payload: list[dict], ttl_seconds: int) -> None:
        _ = (key, payload, ttl_seconds)


class DjangoExternalSearchCacheBackend(ExternalSearchCacheBackend):
    def get(self, key: str) -> list[dict] | None:
        cached_payload = cache.get(key)
        if isinstance(cached_payload, list):
            return cached_payload
        return None

    def set(self, key: str, payload: list[dict], ttl_seconds: int) -> None:
        cache.set(key, payload, timeout=ttl_seconds)


class ExternalSourceAdapter(ABC):
    source_name: str = ""
    implemented: bool = False

    @abstractmethod
    def search_actor_items(
        self, *, actor: Actor, page: int, ordering: str
    ) -> list[dict]:
        raise NotImplementedError

    @abstractmethod
    def search_genre_items(
        self, *, genre: Genre, page: int, ordering: str
    ) -> list[dict]:
        raise NotImplementedError


class PlaceholderExternalSourceAdapter(ExternalSourceAdapter):
    def __init__(self, source_name: str):
        self.source_name = source_name
        self.implemented = False

    def search_actor_items(
        self, *, actor: Actor, page: int, ordering: str
    ) -> list[dict]:
        _ = (actor, page, ordering)
        return []

    def search_genre_items(
        self, *, genre: Genre, page: int, ordering: str
    ) -> list[dict]:
        _ = (genre, page, ordering)
        return []


class JableExternalSourceAdapter(ExternalSourceAdapter):
    source_name = "jable"
    implemented = True

    def search_actor_items(
        self, *, actor: Actor, page: int, ordering: str
    ) -> list[dict]:
        jable = self._get_jable_source()
        if jable is None:
            return []

        actor_pk = self._get_model_pk(actor)
        if actor_pk is None:
            return []

        sort_by = self._map_ordering_to_jable(ordering)
        mapping = actor_source_mapping_service.get_actor_source_mappings(
            actor_ids=[actor_pk],
            source_name=self.source_name,
        ).get(actor_pk)
        if mapping is not None and mapping.source_actor_slug:
            records = jable.get_model_videos(
                model_slug=mapping.source_actor_slug,
                page=page,
                sort_by=sort_by,
            )
            return self._normalize_items(records)

        return self._normalize_items(jable.search(actor.name, page=page))

    def search_genre_items(
        self, *, genre: Genre, page: int, ordering: str
    ) -> list[dict]:
        _ = ordering
        jable = self._get_jable_source()
        if jable is None:
            return []

        genre_pk = self._get_model_pk(genre)
        if genre_pk is None:
            return []

        mapping = genre_source_mapping_service.get_genre_source_mappings(
            genre_ids=[genre_pk],
            source_name=self.source_name,
        ).get(genre_pk)
        if mapping is None or not mapping.source_genre_slug:
            return self._normalize_items(jable.search(genre.name, page=page))

        source_url = str(mapping.source_genre_url or "").strip().lower()
        slug = mapping.source_genre_slug

        if "/categories/" in source_url:
            records = jable.get_category_videos(slug, page=page)
            return self._normalize_items(records)
        if "/tags/" in source_url:
            records = jable.get_tag_videos(slug, page=page)
            return self._normalize_items(records)

        records = jable.get_tag_videos(slug, page=page)
        if records:
            return self._normalize_items(records)
        return self._normalize_items(jable.get_category_videos(slug, page=page))

    def _get_jable_source(self) -> "JableSearchProtocol | None":
        for source in source_manager.sources.values():
            source_name = getattr(source, "get_source_name", lambda: "")()
            if str(source_name).strip().lower() == self.source_name:
                return cast("JableSearchProtocol", source)
        logger.warning("Jable source is unavailable in SourceManager")
        return None

    def _get_model_pk(self, instance: Any) -> int | None:
        raw_pk = getattr(instance, "pk", None)
        if raw_pk is None:
            return None
        try:
            return int(raw_pk)
        except (TypeError, ValueError):
            return None

    def _map_ordering_to_jable(self, ordering: str) -> str:
        normalized_ordering = str(ordering or "").strip().lower()
        if normalized_ordering in {
            "latest",
            "-latest",
            "release_date",
            "-release_date",
        }:
            return "post_date"
        return "video_viewed"

    def _normalize_items(self, raw_items: list[dict]) -> list[dict]:
        output: list[dict] = []
        for item in raw_items:
            metrics = dict(item.get("metrics") or {})
            output.append(
                {
                    "avid": str(item.get("avid", "")).strip().upper(),
                    "original_title": "",
                    "source_title": str(item.get("title", "")).strip(),
                    "translated_title": "",
                    "source": str(item.get("source", "Jable")).strip() or "Jable",
                    "release_date": "",
                    "has_video": False,
                    "watched": False,
                    "is_favorite": False,
                    "metadata_create_time": None,
                    "metadata_update_time": None,
                    "video_create_time": None,
                    "genres": [],
                    "thumbnail_url": str(item.get("cover_url", "")).strip(),
                    "detail_url": str(item.get("detail_url", "")).strip(),
                    "metrics": metrics,
                }
            )
        return [item for item in output if item["avid"]]


class ExternalSearchService:
    DEFAULT_CACHE_TTL_SECONDS = 300
    DEFAULT_FETCH_PAGES = 5
    DEFAULT_PAGE_SIZE = 20
    MAX_PAGE_SIZE = 100

    def __init__(self):
        self.adapters: dict[str, ExternalSourceAdapter] = {
            "jable": JableExternalSourceAdapter(),
            "missav": PlaceholderExternalSourceAdapter("missav"),
            "memo": PlaceholderExternalSourceAdapter("memo"),
        }

    def search_actor_detail(
        self,
        *,
        actor_id: int,
        source_name: str,
        page: int,
        page_size: int,
        ordering: str,
    ) -> ExternalSearchResult:
        actor = (
            Actor.objects.annotate(resource_count=Count("resources"))
            .filter(pk=actor_id)
            .first()
        )
        if actor is None:
            raise Actor.DoesNotExist
        actor_pk = self._model_pk_or_zero(actor)

        result = self._search_items(
            entity_type="actor",
            entity_id=actor_pk,
            source_name=source_name,
            page=page,
            page_size=page_size,
            ordering=ordering,
            fetch_page=lambda target_page, requested_ordering: self.adapters[
                self._normalize_source(source_name)
            ].search_actor_items(
                actor=actor,
                page=target_page,
                ordering=requested_ordering,
            ),
        )
        result.meta["actor"] = {
            "id": actor_pk,
            "name": actor.name,
            "resource_count": getattr(actor, "resource_count", 0),
            "avatar_url": actor.avatar_url,
            "avatar_filename": actor.avatar_filename,
        }
        return result

    def search_genre_detail(
        self,
        *,
        genre_id: int,
        source_name: str,
        page: int,
        page_size: int,
        ordering: str,
    ) -> ExternalSearchResult:
        genre = (
            Genre.objects.annotate(resource_count=Count("resources"))
            .filter(pk=genre_id)
            .first()
        )
        if genre is None:
            raise Genre.DoesNotExist
        genre_pk = self._model_pk_or_zero(genre)

        result = self._search_items(
            entity_type="genre",
            entity_id=genre_pk,
            source_name=source_name,
            page=page,
            page_size=page_size,
            ordering=ordering,
            fetch_page=lambda target_page, requested_ordering: self.adapters[
                self._normalize_source(source_name)
            ].search_genre_items(
                genre=genre,
                page=target_page,
                ordering=requested_ordering,
            ),
        )
        result.meta["genre"] = {
            "id": genre_pk,
            "name": genre.name,
            "resource_count": getattr(genre, "resource_count", 0),
        }
        return result

    def _model_pk_or_zero(self, instance: Any) -> int:
        raw_pk = getattr(instance, "pk", 0)
        if raw_pk is None:
            return 0
        try:
            return int(raw_pk)
        except (TypeError, ValueError):
            return 0

    def _search_items(
        self,
        *,
        entity_type: str,
        entity_id: int,
        source_name: str,
        page: int,
        page_size: int,
        ordering: str,
        fetch_page,
    ) -> ExternalSearchResult:
        normalized_source = self._normalize_source(source_name)
        adapter = self.adapters.get(normalized_source)
        safe_page, safe_page_size, safe_ordering = self._normalize_query_params(
            page=page,
            page_size=page_size,
            ordering=ordering,
        )

        if adapter is None:
            return ExternalSearchResult(
                items=[],
                pagination=self._empty_pagination(safe_page, safe_page_size),
                meta={
                    "source": normalized_source,
                    "implemented": False,
                    "message": "source_not_supported",
                    "supported_sources": sorted(self.adapters.keys()),
                    "cache": {"enabled": False, "hit": False},
                },
            )

        if not adapter.implemented:
            return ExternalSearchResult(
                items=[],
                pagination=self._empty_pagination(safe_page, safe_page_size),
                meta={
                    "source": normalized_source,
                    "implemented": False,
                    "message": "source_adapter_not_implemented",
                    "cache": {"enabled": False, "hit": False},
                },
            )

        fetch_pages = self._fetch_pages_limit()
        cache_enabled = self._cache_enabled()
        cache_ttl = self._cache_ttl_seconds()
        cache_backend = (
            DjangoExternalSearchCacheBackend()
            if cache_enabled
            else NoopExternalSearchCacheBackend()
        )

        cache_key = (
            "external-search:"
            f"{entity_type}:{entity_id}:{normalized_source}:"
            f"{fetch_pages}:{safe_ordering}"
        )
        cache_hit = False
        normalized_items = cache_backend.get(cache_key)
        if normalized_items is not None:
            cache_hit = True
        else:
            normalized_items = self._collect_items(
                fetch_page=fetch_page,
                ordering=safe_ordering,
                fetch_pages=fetch_pages,
            )
            cache_backend.set(cache_key, normalized_items, cache_ttl)

        sorted_items = self._sort_items(normalized_items, safe_ordering)
        page_items, pagination = self._paginate(
            sorted_items,
            page=safe_page,
            page_size=safe_page_size,
        )
        return ExternalSearchResult(
            items=page_items,
            pagination=pagination,
            meta={
                "source": normalized_source,
                "implemented": True,
                "ordering": safe_ordering,
                "fetch_pages": fetch_pages,
                "cache": {"enabled": cache_enabled, "hit": cache_hit},
            },
        )

    def _collect_items(
        self, *, fetch_page, ordering: str, fetch_pages: int
    ) -> list[dict]:
        _ = ordering
        merged: list[dict] = []
        seen: set[str] = set()

        for target_page in range(1, fetch_pages + 1):
            try:
                page_items = fetch_page(target_page, ordering)
            except Exception as error:
                logger.warning(
                    "external search page fetch failed. page=%s error=%s",
                    target_page,
                    error,
                )
                break
            if not page_items:
                break

            new_count = 0
            for item in page_items:
                avid = str(item.get("avid", "")).strip().upper()
                if not avid or avid in seen:
                    continue
                seen.add(avid)
                merged.append(item)
                new_count += 1

            if new_count == 0:
                break

        return merged

    def _sort_items(self, items: list[dict], ordering: str) -> list[dict]:
        normalized = str(ordering or "").strip()
        descending = normalized.startswith("-")
        field = normalized[1:] if descending else normalized
        field = field or "views"

        def to_int(value: Any) -> int:
            try:
                return int(value)
            except (TypeError, ValueError):
                return 0

        def sort_key(item: dict):
            metrics = dict(item.get("metrics") or {})
            if field == "avid":
                return str(item.get("avid", "")).upper()
            if field in {"title", "source_title"}:
                return str(item.get("source_title", "")).strip().lower()
            if field == "likes":
                return to_int(metrics.get("likes"))
            if field in {"latest", "release_date"}:
                return str(item.get("release_date", "")).strip()
            return to_int(metrics.get("views"))

        return sorted(items, key=sort_key, reverse=descending)

    def _paginate(
        self,
        items: list[dict],
        *,
        page: int,
        page_size: int,
    ) -> tuple[list[dict], dict[str, int]]:
        total = len(items)
        pages = max((total + page_size - 1) // page_size, 1)
        start = (page - 1) * page_size
        end = start + page_size
        return items[start:end], {
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": pages,
        }

    def _empty_pagination(self, page: int, page_size: int) -> dict[str, int]:
        return {
            "total": 0,
            "page": page,
            "page_size": page_size,
            "pages": 1,
        }

    def _normalize_query_params(
        self,
        *,
        page: int,
        page_size: int,
        ordering: str,
    ) -> tuple[int, int, str]:
        safe_page = max(int(page or 1), 1)
        safe_page_size = max(
            1, min(int(page_size or self.DEFAULT_PAGE_SIZE), self.MAX_PAGE_SIZE)
        )
        normalized_ordering = str(ordering or "").strip()
        if not normalized_ordering:
            normalized_ordering = "-views"
        return safe_page, safe_page_size, normalized_ordering

    def _normalize_source(self, source_name: str) -> str:
        normalized = str(source_name or "jable").strip().lower()
        return normalized or "jable"

    def _cache_enabled(self) -> bool:
        return bool(getattr(settings, "EXTERNAL_SEARCH_CACHE_ENABLED", False))

    def _cache_ttl_seconds(self) -> int:
        try:
            ttl = int(
                getattr(
                    settings,
                    "EXTERNAL_SEARCH_CACHE_TTL_SECONDS",
                    self.DEFAULT_CACHE_TTL_SECONDS,
                )
            )
        except (TypeError, ValueError):
            ttl = self.DEFAULT_CACHE_TTL_SECONDS
        return max(ttl, 1)

    def _fetch_pages_limit(self) -> int:
        try:
            pages = int(
                getattr(
                    settings, "EXTERNAL_SEARCH_FETCH_PAGES", self.DEFAULT_FETCH_PAGES
                )
            )
        except (TypeError, ValueError):
            pages = self.DEFAULT_FETCH_PAGES
        return max(pages, 1)


external_search_service = ExternalSearchService()


class JableSearchProtocol(Protocol):
    def get_model_videos(
        self,
        model_slug: str,
        page: int = 1,
        sort_by: str = "video_viewed",
    ) -> list[dict]: ...

    def search(self, keyword: str, page: int = 1) -> list[dict]: ...

    def get_tag_videos(self, tag_slug: str, page: int = 1) -> list[dict]: ...

    def get_category_videos(
        self,
        category_slug: str,
        page: int = 1,
    ) -> list[dict]: ...
