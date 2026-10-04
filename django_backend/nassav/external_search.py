from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
import re
from dataclasses import dataclass
from typing import Any, cast

from django.conf import settings
from django.core.cache import cache
from django.db.models import Count
from loguru import logger

from nassav.models import AVResource, Actor, Genre
from nassav.recommendation.actor_source_mapping import actor_source_mapping_service
from nassav.recommendation.genre_source_mapping import genre_source_mapping_service
from nassav.source.SourceManager import source_manager
from nassav.source.SourceBase import SourceBase
from nassav.source.capabilities import ListingSource
from nassav.composition import external_search_adapters
from nassav.source.CookieRepository import proxy_route_profile
from nassav.source.search_contracts import SourceSearchError, SourceSearchUnavailable


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


@dataclass(frozen=True)
class SearchCapability:
    source: str
    label: str
    actor: bool = True
    genre: bool = True
    orderings: tuple[str, ...] = (
        "-views",
        "views",
        "-likes",
        "likes",
        "-latest",
        "latest",
    )
    native_order: bool = False

    def public_payload(self) -> dict:
        return {
            "source": self.source,
            "label": self.label,
            "actor": self.actor,
            "genre": self.genre,
            "orderings": list(self.orderings),
        }


class ExternalSourceAdapter(ABC):
    source_name: str = ""
    implemented: bool = False

    def __init__(
        self, *, source_lookup: Callable[[str], SourceBase | None] | None = None
    ):
        self.source_lookup = (
            source_lookup if source_lookup is not None else source_manager.get_source
        )

    def capability(self) -> SearchCapability:
        return SearchCapability(self.source_name, self.source_name)

    def is_enabled(self) -> bool:
        return self.source_lookup(self.source_name) is not None

    def cache_context(self) -> tuple[str, str]:
        source = self.source_lookup(self.source_name)
        if source is None:
            raise SourceSearchUnavailable("source_disabled")
        return (
            getattr(source, "domain", ""),
            proxy_route_profile(getattr(source, "proxy", None)) or "direct",
        )

    def validate_ordering(self, ordering: str) -> None:
        # Preserve legacy client sorting (including title/AVID) by default.
        pass

    @abstractmethod
    def search_actor_items(
        self, *, actor: Actor, page: int, ordering: str, force_refresh: bool = False
    ) -> list[dict]:
        raise NotImplementedError

    @abstractmethod
    def search_genre_items(
        self, *, genre: Genre, page: int, ordering: str, force_refresh: bool = False
    ) -> list[dict]:
        raise NotImplementedError

    def _normalize_items(self, raw_items: list[dict]) -> list[dict]:
        output: list[dict] = []
        for item in raw_items:
            metrics = dict(item.get("metrics") or {})
            output.append(
                {
                    "avid": str(item.get("avid", "")).strip().upper(),
                    "source_title": str(item.get("title", "")).strip(),
                    "source": str(item.get("source", self.source_name)).strip()
                    or self.source_name,
                    "thumbnail_url": str(item.get("cover_url", "")).strip(),
                    "detail_url": str(item.get("detail_url", "")).strip(),
                    "metrics": metrics,
                }
            )
        valid_items = [item for item in output if item["avid"]]
        self._attach_library_presence(valid_items)
        return valid_items

    def _attach_library_presence(self, items: list[dict]) -> None:
        avids = [str(item.get("avid", "")).strip().upper() for item in items]
        valid_avids = [avid for avid in avids if avid]
        if not valid_avids:
            return

        existing_avids = {
            str(avid).strip().upper()
            for avid in AVResource.objects.filter(avid__in=valid_avids).values_list(
                "avid",
                flat=True,
            )
        }
        for item in items:
            avid = str(item.get("avid", "")).strip().upper()
            item["in_library"] = avid in existing_avids


class PlaceholderExternalSourceAdapter(ExternalSourceAdapter):
    def __init__(self, source_name: str):
        self.source_name = source_name
        self.implemented = False

    def search_actor_items(
        self, *, actor: Actor, page: int, ordering: str, force_refresh: bool = False
    ) -> list[dict]:
        _ = (actor, page, ordering, force_refresh)
        return []

    def search_genre_items(
        self, *, genre: Genre, page: int, ordering: str, force_refresh: bool = False
    ) -> list[dict]:
        _ = (genre, page, ordering, force_refresh)
        return []


class JableExternalSourceAdapter(ExternalSourceAdapter):
    source_name = "jable"
    implemented = True

    def capability(self) -> SearchCapability:
        return SearchCapability(self.source_name, "Jable")

    def search_actor_items(
        self, *, actor: Actor, page: int, ordering: str, force_refresh: bool = False
    ) -> list[dict]:
        jable = self._get_jable_source()
        if jable is None:
            raise SourceSearchUnavailable("source_disabled")

        actor_pk = self._get_model_pk(actor)
        if actor_pk is None:
            return []

        sort_by = self._map_ordering_to_jable(ordering)
        mapping = actor_source_mapping_service.get_actor_source_mappings(
            actor_ids=[actor_pk],
            source_name=self.source_name,
        ).get(actor_pk)
        if mapping is not None and mapping.source_actor_slug:
            records = self._call_get_model_videos(
                jable=jable,
                model_slug=mapping.source_actor_slug,
                page=page,
                sort_by=sort_by,
                force_refresh=force_refresh,
            )
            return self._normalize_items(records)

        return self._normalize_items(
            self._call_search(
                jable=jable,
                keyword=actor.name,
                page=page,
                force_refresh=force_refresh,
            )
        )

    def search_genre_items(
        self, *, genre: Genre, page: int, ordering: str, force_refresh: bool = False
    ) -> list[dict]:
        _ = ordering
        jable = self._get_jable_source()
        if jable is None:
            raise SourceSearchUnavailable("source_disabled")

        genre_pk = self._get_model_pk(genre)
        if genre_pk is None:
            return []

        mapping = genre_source_mapping_service.get_genre_source_mappings(
            genre_ids=[genre_pk],
            source_name=self.source_name,
        ).get(genre_pk)
        if mapping is None or not mapping.source_genre_slug:
            return self._normalize_items(
                self._call_search(
                    jable=jable,
                    keyword=genre.name,
                    page=page,
                    force_refresh=force_refresh,
                )
            )

        source_url = str(mapping.source_genre_url or "").strip().lower()
        slug = mapping.source_genre_slug

        if "/categories/" in source_url:
            records = self._call_get_category_videos(
                jable=jable,
                category_slug=slug,
                page=page,
                force_refresh=force_refresh,
            )
            return self._normalize_items(records)
        if "/tags/" in source_url:
            records = self._call_get_tag_videos(
                jable=jable,
                tag_slug=slug,
                page=page,
                force_refresh=force_refresh,
            )
            return self._normalize_items(records)

        records = self._call_get_tag_videos(
            jable=jable,
            tag_slug=slug,
            page=page,
            force_refresh=force_refresh,
        )
        if records:
            return self._normalize_items(records)
        return self._normalize_items(
            self._call_get_category_videos(
                jable=jable,
                category_slug=slug,
                page=page,
                force_refresh=force_refresh,
            )
        )

    def _call_get_model_videos(
        self,
        *,
        jable: ListingSource,
        model_slug: str,
        page: int,
        sort_by: str,
        force_refresh: bool,
    ) -> list[dict]:
        return jable.search_listing(
            "models",
            model_slug,
            page=page,
            ordering=sort_by,
            force_refresh=force_refresh,
        )

    def _call_search(
        self, *, jable: ListingSource, keyword: str, page: int, force_refresh: bool
    ) -> list[dict]:
        return jable.search_listing(
            "search", keyword, page=page, force_refresh=force_refresh
        )

    def _call_get_tag_videos(
        self, *, jable: ListingSource, tag_slug: str, page: int, force_refresh: bool
    ) -> list[dict]:
        return jable.search_listing(
            "tags", tag_slug, page=page, force_refresh=force_refresh
        )

    def _call_get_category_videos(
        self,
        *,
        jable: ListingSource,
        category_slug: str,
        page: int,
        force_refresh: bool,
    ) -> list[dict]:
        return jable.search_listing(
            "categories", category_slug, page=page, force_refresh=force_refresh
        )

    def _get_jable_source(self) -> ListingSource | None:
        source = self.source_lookup(self.source_name)
        if source is None:
            logger.warning("Jable source is unavailable in SourceManager")
            return None
        if not isinstance(source, ListingSource):
            raise SourceSearchUnavailable("source_adapter_not_implemented")
        if isinstance(source, SourceBase):
            source_manager.refresh_source_session(source.get_source_name())
        return source

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


class MissAVExternalSourceAdapter(ExternalSourceAdapter):
    source_name = "missav"
    implemented = True

    def capability(self) -> SearchCapability:
        return SearchCapability(
            self.source_name,
            "MissAV",
            orderings=("-views", "-likes", "-latest"),
            native_order=True,
        )

    def validate_ordering(self, ordering: str) -> None:
        if ordering not in self.capability().orderings:
            raise ValueError("MissAV supports descending views, likes and latest only")

    def search_actor_items(
        self, *, actor: Actor, page: int, ordering: str, force_refresh: bool = False
    ) -> list[dict]:
        mapping = actor_source_mapping_service.get_actor_source_mappings(
            actor_ids=[cast(int, actor.pk)],
            source_name=self.source_name,
        ).get(cast(int, actor.pk))
        term = (
            mapping.source_actor_slug
            if mapping and mapping.source_actor_slug
            else actor.name
        )
        kind = "actresses" if mapping and mapping.source_actor_slug else "search"
        return self._search(kind, term, page, ordering, force_refresh)

    def search_genre_items(
        self, *, genre: Genre, page: int, ordering: str, force_refresh: bool = False
    ) -> list[dict]:
        mapping = genre_source_mapping_service.get_genre_source_mappings(
            genre_ids=[cast(int, genre.pk)],
            source_name=self.source_name,
        ).get(cast(int, genre.pk))
        term = (
            mapping.source_genre_slug
            if mapping and mapping.source_genre_slug
            else genre.name
        )
        kind = "genres" if mapping and mapping.source_genre_slug else "search"
        return self._search(kind, term, page, ordering, force_refresh)

    def _search(
        self, kind: str, term: str, page: int, ordering: str, force_refresh: bool
    ) -> list[dict]:
        source = self.source_lookup(self.source_name)
        if source is None:
            raise SourceSearchUnavailable("source_disabled")
        if isinstance(source, SourceBase):
            source_manager.refresh_source_session(source.get_source_name())
        items = cast(SourceBase, source).search_listing(
            kind,
            term,
            page=page,
            ordering=ordering,
            force_refresh=force_refresh,
        )
        return self._normalize_items(items)


class ExternalSearchService:
    DEFAULT_CACHE_TTL_SECONDS = 300
    DEFAULT_FETCH_PAGES = 5
    DEFAULT_PAGE_SIZE = 20
    MAX_PAGE_SIZE = 100

    def default_source(self, entity_type: str) -> str:
        from nassav.user_settings import get_settings_manager

        preferred = (
            get_settings_manager()
            .get_all()
            .get("default_external_search_source", "jable")
        )
        enabled = [
            entry["source"] for entry in self.capabilities() if entry.get(entity_type)
        ]
        return (
            preferred
            if preferred in enabled
            else (enabled[0] if enabled else preferred)
        )

    def __init__(self, *, adapters: Mapping[str, ExternalSourceAdapter] | None = None):
        self.adapters = (
            dict(adapters) if adapters is not None else external_search_adapters()
        )

    def capabilities(self) -> list[dict]:
        return [
            adapter.capability().public_payload()
            for adapter in self.adapters.values()
            if adapter.implemented and adapter.is_enabled()
        ]

    def registered_sources(self) -> set[str]:
        return {name for name, adapter in self.adapters.items() if adapter.implemented}

    def cache_context(self, source_name: str) -> tuple[str, str]:
        return self.adapters[source_name].cache_context()

    def search_actor_detail(
        self,
        *,
        actor_id: int,
        source_name: str,
        page: int,
        page_size: int,
        ordering: str,
        force_refresh: bool = False,
        on_progress: Callable[[ExternalSearchResult], None] | None = None,
        should_cancel: Callable[[], None] | None = None,
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
                force_refresh=force_refresh,
            ),
            force_refresh=force_refresh,
            on_progress=on_progress,
            should_cancel=should_cancel,
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
        force_refresh: bool = False,
        on_progress: Callable[[ExternalSearchResult], None] | None = None,
        should_cancel: Callable[[], None] | None = None,
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
                force_refresh=force_refresh,
            ),
            force_refresh=force_refresh,
            on_progress=on_progress,
            should_cancel=should_cancel,
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
        force_refresh: bool = False,
        on_progress: Callable[[ExternalSearchResult], None] | None = None,
        should_cancel: Callable[[], None] | None = None,
    ) -> ExternalSearchResult:
        normalized_source = self._normalize_source(source_name)
        adapter = self.adapters.get(normalized_source)
        safe_page, safe_page_size, safe_ordering = self._normalize_query_params(
            page=page,
            page_size=page_size,
            ordering=ordering,
        )

        if adapter is None:
            raise ValueError("source_not_supported")
        if not adapter.implemented:
            raise SourceSearchUnavailable("source_adapter_not_implemented")
        capability = next(
            (
                entry
                for entry in self.capabilities()
                if entry["source"] == normalized_source
            ),
            None,
        )
        if capability is None:
            raise SourceSearchUnavailable("source_disabled")
        adapter.validate_ordering(safe_ordering)
        source_native_order = adapter.capability().native_order

        fetch_pages = self._fetch_pages_limit()
        cache_enabled = self._cache_enabled()
        cache_ttl = self._cache_ttl_seconds()
        cache_backend = (
            DjangoExternalSearchCacheBackend()
            if cache_enabled
            else NoopExternalSearchCacheBackend()
        )

        domain, route = adapter.cache_context()
        cache_key = (
            "external-search:v4:cn:"
            f"{entity_type}:{entity_id}:{normalized_source}:{domain}:{route}:"
            f"{fetch_pages}:{safe_ordering}"
        )
        cache_hit = False
        normalized_items: list[dict] | None = None
        if not force_refresh:
            normalized_items = cache_backend.get(cache_key)
            if normalized_items is not None:
                cache_hit = True

        def report_progress(items: list[dict], completed: int) -> None:
            if on_progress is None:
                return
            ordered = (
                items if source_native_order else self._sort_items(items, safe_ordering)
            )
            visible, pagination = self._paginate(
                ordered, page=safe_page, page_size=safe_page_size
            )
            on_progress(
                ExternalSearchResult(
                    items=visible,
                    pagination=pagination,
                    meta={
                        "source": normalized_source,
                        "implemented": True,
                        "ordering": safe_ordering,
                        "fetch_pages": fetch_pages,
                        "pages_completed": completed,
                        "partial": True,
                        "cache": {
                            "enabled": cache_enabled,
                            "hit": False,
                            "force_refresh": force_refresh,
                        },
                    },
                )
            )

        if normalized_items is None:
            if should_cancel is not None:
                should_cancel()
            normalized_items = self._collect_items(
                fetch_page=fetch_page,
                ordering=safe_ordering,
                fetch_pages=fetch_pages,
                on_progress=report_progress if on_progress is not None else None,
                should_cancel=should_cancel,
            )
            if should_cancel is not None:
                should_cancel()
            cache_backend.set(cache_key, normalized_items, cache_ttl)

        sorted_items = (
            normalized_items
            if source_native_order
            else self._sort_items(normalized_items, safe_ordering)
        )
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
                "partial": False,
                "ordering": safe_ordering,
                "fetch_pages": fetch_pages,
                "cache": {
                    "enabled": cache_enabled,
                    "hit": cache_hit,
                    "force_refresh": force_refresh,
                },
            },
        )

    def _collect_items(
        self,
        *,
        fetch_page,
        ordering: str,
        fetch_pages: int,
        on_progress: Callable[[list[dict], int], None] | None = None,
        should_cancel: Callable[[], None] | None = None,
    ) -> list[dict]:
        _ = ordering
        merged: list[dict] = []
        seen: set[str] = set()

        for target_page in range(1, fetch_pages + 1):
            if should_cancel is not None:
                should_cancel()
            try:
                page_items = fetch_page(target_page, ordering)
            except Exception as error:
                logger.warning(
                    "External search page {} failed: {} reason={}",
                    target_page,
                    type(error).__name__,
                    str(error)
                    if isinstance(error, SourceSearchError)
                    and re.fullmatch(r"[A-Za-z0-9_.:-]{1,100}", str(error))
                    else "unclassified",
                )
                if isinstance(error, (SourceSearchError, ValueError)):
                    raise
                raise SourceSearchError("source_fetch_failed") from error
            if should_cancel is not None:
                should_cancel()
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

            if on_progress is not None:
                on_progress(list(merged), target_page)
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
