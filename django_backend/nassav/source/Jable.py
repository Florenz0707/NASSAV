import re
from collections.abc import Callable
from copy import deepcopy
from urllib.parse import quote, urlencode, urljoin
from uuid import uuid4

from bs4 import BeautifulSoup
from django.conf import settings
from django.core.cache import cache
from loguru import logger

from nassav.page_fetching import (
    PageFetchService,
    create_page_fetch_service,
    validate_strategy,
)
from nassav.page_fetching.coordination import SessionRefreshCoordinator
from nassav.recommendation.contracts import RecommendationSource
from nassav.resource_contracts import SourceRelations
from nassav.scraper.AVDownloadInfo import AVDownloadInfo
from nassav.source.capabilities import ListingSource
from nassav.source.CookieRepository import CookieRepository
from nassav.source.jable_actor_mapping import parse_jable_model_candidates
from nassav.source.search_contracts import SourceSearchError
from nassav.source.SourceBase import SourceBase


class Jable(SourceBase, ListingSource, RecommendationSource):
    """Jable下载器"""

    HOT_BOARD_SORTS = [
        "video_viewed_today",
        "video_viewed_week",
        "video_viewed_month",
        "video_viewed",
    ]

    DEFAULT_DOMAIN = "jable.tv"

    def __init__(
        self,
        proxy: str | None = None,
        timeout: int = 15,
        *,
        strict_failures: bool = False,
        page_fetcher: PageFetchService | None = None,
        cookie_repository: CookieRepository | None = None,
        refresh_coordinator: SessionRefreshCoordinator | None = None,
        facts_cache=None,
    ):
        super().__init__(
            proxy,
            timeout,
            cookie_repository=cookie_repository,
            refresh_coordinator=refresh_coordinator,
        )
        self.facts_cache = facts_cache
        self.strict_failures = strict_failures
        source_config = settings.SOURCE_CONFIG.get("jable", {})
        self.domain = source_config.get("domain", self.DEFAULT_DOMAIN)
        self.browser_fetch_strategy = validate_strategy(
            source_config.get("browser_fetch_strategy", "direct_first")
        )
        self.page_fetcher = page_fetcher or create_page_fetch_service(
            settings.BROWSER_FETCH_CONFIG, proxy_url=proxy
        )
        self.cache_enabled = bool(
            getattr(settings, "EXTERNAL_SOURCE_SEARCH_CACHE_ENABLED", True)
        )
        self.cache_ttl_default = int(
            getattr(settings, "EXTERNAL_SOURCE_SEARCH_CACHE_TTL_DEFAULT", 1800)
        )
        self.cache_ttl_hot = int(
            getattr(settings, "EXTERNAL_SOURCE_SEARCH_CACHE_TTL_HOT", 300)
        )
        self.cache_ttl_latest = int(
            getattr(settings, "EXTERNAL_SOURCE_SEARCH_CACHE_TTL_LATEST", 300)
        )

    def get_source_name(self) -> str:
        return "Jable"

    def set_cookie_auto(
        self,
        force_refresh: bool = False,
        *,
        write_guard: Callable[[], bool] | None = None,
    ) -> bool:
        """Acquire and verify a paired browser session for explicit refreshes."""
        if self.credential_context is not None:
            return False
        if self.page_fetcher.browser is None:
            return super().set_cookie_auto(force_refresh, write_guard=write_guard)
        record = self._sessions.repository.get_cookie_record(self.get_source_name())
        if not force_refresh and record is not None and record.cookie:
            self.set_session(record)
            return True
        expected_version = record.updated_at if record is not None else None
        url = self.get_home_url()
        result = PageFetchService.validate_result(
            url,
            self.page_fetcher.browser.fetch(
                url, timeout_ms=self.page_fetcher.timeout_ms
            ),
            self._is_listing_page_html,
        )
        if not result.ok:
            return False
        return self.accept_browser_session(
            url,
            result,
            self._is_listing_page_html,
            expected_version,
            write_guard=write_guard,
        )

    def search_listing(
        self,
        kind: str,
        term: str,
        *,
        page: int = 1,
        ordering: str = "-views",
        force_refresh: bool = False,
    ) -> list[dict]:
        """Expose failures to external search while retaining legacy list callers."""
        self._request_state.listing_failure = None
        if kind == "models":
            items = self.get_model_videos(
                term, page, ordering, force_refresh=force_refresh
            )
        elif kind == "tags":
            items = self.get_tag_videos(term, page, force_refresh=force_refresh)
        elif kind == "categories":
            items = self.get_category_videos(term, page, force_refresh=force_refresh)
        elif kind == "search":
            items = self.search(term, page, force_refresh=force_refresh)
        else:
            raise ValueError("Unsupported Jable listing kind")
        failure = self._request_state.listing_failure
        if failure is not None:
            raise SourceSearchError(f"jable_listing_{failure}")
        return items

    def parse_relations(self, html: str) -> SourceRelations:
        candidates = parse_jable_model_candidates(
            html, base_url=f"https://{self.domain}/"
        )
        names = tuple(
            dict.fromkeys(
                candidate.source_actor_name.strip()
                for candidate in candidates
                if candidate.source_actor_name.strip()
            )
        )
        return SourceRelations(names, tuple(candidates))

    def get_html(self, avid: str) -> str | None:
        urls = [
            f"https://{self.domain}/videos/{avid.lower()}/",
            f"https://{self.domain}/videos/{avid.lower()}v/",
            f"https://{self.domain}/videos/{avid.lower()}bf/",
            f"https://{self.domain}/videos/{avid.lower()}ntum/",
        ]
        fetcher = self.page_fetcher.for_lookup()
        request_id = uuid4().hex[:12]
        for candidate_index, url in enumerate(urls, start=1):
            result = self._request_html(
                url,
                referer=f"https://{self.domain}/search/{avid.lower()}",
                validator=self._is_detail_page_html,
                fetcher=fetcher,
                candidate_index=candidate_index,
                request_id=request_id,
            )
            if result:
                return result
        return None

    def parse_html(self, html: str) -> AVDownloadInfo | None:
        """解析 HTML 获取核心下载信息（m3u8、avid、source_title）

        其他元数据（发行日期、时长、演员等）由 JavBus Scraper 提供
        """
        info = AVDownloadInfo()
        info.source = self.get_source_name()

        try:
            # 1. 提取 m3u8（必需）
            match = re.search(r'var hlsUrl = ["\']([^"\']+)["\']', html)
            if match:
                info.m3u8 = match.group(1)
            else:
                return None

            # 2. 提取 source_title（备用标题）- 优先从 <title> 标签提取
            # 格式: <title>AVID 标题内容 - Jable.TV | ...</title>
            title_match = re.search(r"<title>(.+?)\s*-\s*Jable\.TV", html)
            if title_match:
                full_title = title_match.group(1).strip()
                info.source_title = full_title

                # 3. 从标题中提取 AVID
                avid_match = re.match(r"^([A-Z]+-\d+)\s+(.+)$", full_title)
                if avid_match:
                    info.avid = avid_match.group(1)
                    info.source_title = avid_match.group(2).strip()

            # 如果标题提取失败，尝试其他模式
            if not info.source_title:
                title_patterns = [
                    r'<h4 class="title">([^<]+)</h4>',
                    r'<span class="font-medium">([^<]+)</span>',
                ]
                for pattern in title_patterns:
                    title_match = re.search(pattern, html)
                    if title_match:
                        info.source_title = title_match.group(1).strip()
                        break

            # 如果 AVID 还未提取，单独查找
            if not info.avid:
                avid_match = re.search(
                    r'<span class="inactive-color">([A-Z]+-\d+)</span>', html
                )
                if avid_match:
                    info.avid = avid_match.group(1)

            return info
        except Exception as e:
            logger.error(f"Jable 解析失败: {e}")
            return None

    def get_cover_url(self, html: str) -> str | None:
        try:
            match = re.search(r'<meta property="og:image" content="([^"]+)"', html)
            if match:
                return match.group(1)
            return None
        except Exception as e:
            logger.error(f"封面URL提取失败: {e}")
            return None

    def get_detail_url(self, avid: str) -> str:
        return f"https://{self.domain}/videos/{avid.lower()}/"

    def cached_video_details(self, candidates):
        if self.facts_cache is None:
            return {}
        from nassav.provider_facts import SourceFactsLookup

        self._check_task()
        return SourceFactsLookup(self.facts_cache, self).read_details(candidates)

    def fetch_provider_facts(self, avid: str, detail_url: str = ""):
        from nassav.provider_facts import parse_source_facts

        html = (
            self._request_html(
                detail_url,
                referer=f"https://{self.domain}/",
                validator=self._is_detail_page_html,
            )
            if detail_url
            else self.get_html(avid)
        )
        self._check_task()
        if not html:
            raise SourceSearchError("jable_detail_unavailable")
        detail = self._parse_video_detail(
            html=html, avid=avid, detail_url=detail_url or self.get_detail_url(avid)
        )
        metadata, playback = parse_source_facts(self, avid, html, detail)
        return metadata, playback, html

    def get_video_detail(
        self,
        avid: str,
        detail_url: str = "",
        *,
        force_refresh: bool = False,
    ) -> dict:
        if self.facts_cache is not None:
            from nassav.provider_facts import SourceFactsLookup

            data, _, _, hit = SourceFactsLookup(self.facts_cache, self).resolve(
                avid, detail_url, force=force_refresh
            )
            return (
                {**data.get("detail", {}), "_provider_cache_hit": hit} if data else {}
            )
        normalized_avid = str(avid or "").strip().upper()
        normalized_url = str(detail_url or "").strip()
        if not normalized_avid and not normalized_url:
            return {}

        cache_key = self._build_cache_key(
            "video_detail_v2",
            avid=normalized_avid,
            url=normalized_url,
        )
        if not force_refresh:
            cached_payload = cache.get(cache_key) if self.cache_enabled else None
            if isinstance(cached_payload, dict):
                return deepcopy(cached_payload)

        html = ""
        if normalized_url:
            html = self._request_html(
                normalized_url,
                referer=f"https://{self.domain}/",
                validator=self._is_detail_page_html,
            )
            html = html or ""
        if not html and normalized_avid:
            html = self.get_html(normalized_avid) or ""
        if not html:
            return {}

        try:
            payload = self._parse_video_detail(
                html=html,
                avid=normalized_avid,
                detail_url=normalized_url,
            )
        except Exception as e:
            logger.error(f"Jable.get_video_detail 解析失败: {e}")
            if self.strict_failures:
                raise SourceSearchError("jable_parse_failed") from e
            return {}

        if self.cache_enabled:
            if self.credential_context is not None:
                self.credential_context.check()
            cache.set(cache_key, deepcopy(payload), timeout=self.cache_ttl_default)
        return payload

    def search(
        self, keyword: str, page: int = 1, *, force_refresh: bool = False
    ) -> list[dict]:
        """搜索 Jable 站内资源。

        返回结构:
        [
            {
                "avid": "ABF-001",
                "title": "...",
                "detail_url": "https://jable.tv/videos/...",
                "cover_url": "https://...",
                "source": "Jable",
                "metrics": {
                    "views": 123456,
                    "likes": 789,
                    "duration": "2:01:02",
                },
            }
        ]
        """
        normalized_keyword = str(keyword or "").strip()
        if not normalized_keyword:
            return []

        cache_key = self._build_cache_key(
            "search",
            keyword=normalized_keyword.casefold(),
            page=page,
        )
        if not force_refresh:
            cached_items = self._get_cached_items(cache_key)
            if cached_items is not None:
                return cached_items

        url = self._build_search_url(normalized_keyword, page)
        referer = f"https://{self.domain}/"
        html = self._request_html(
            url,
            referer=referer,
            validator=self._is_listing_page_html,
        )
        if not html:
            logger.warning(
                f"Jable.search 获取 HTML 失败，当前返回空结果。keyword={keyword}, page={page}"
            )
            return []

        try:
            parsed = self._parse_search_results(html)
            self._set_cached_items(
                cache_key, parsed, ttl_seconds=self.cache_ttl_default
            )
            return parsed
        except Exception as e:
            logger.error(f"Jable.search 解析失败: {e}")
            if self.strict_failures:
                raise SourceSearchError("jable_parse_failed") from e
            return []

    def get_model_videos(
        self,
        model_slug: str,
        page: int = 1,
        sort_by: str = "video_viewed",
        *,
        force_refresh: bool = False,
    ) -> list[dict]:
        normalized_slug = self._normalize_model_slug(model_slug)
        if not normalized_slug:
            return []

        cache_key = self._build_cache_key(
            "model_videos",
            slug=normalized_slug,
            page=page,
            sort_by=sort_by,
        )
        if not force_refresh:
            cached_items = self._get_cached_items(cache_key)
            if cached_items is not None:
                return cached_items

        url = self._build_model_videos_url(
            model_slug=normalized_slug,
            page=page,
            sort_by=sort_by,
        )
        referer = f"https://{self.domain}/models/{quote(normalized_slug)}/"
        html = self._request_html(
            url,
            referer=referer,
            validator=self._is_listing_page_html,
        )
        if not html:
            logger.warning(
                "Jable.get_model_videos 获取 HTML 失败，当前返回空结果。"
                f" model_slug={normalized_slug}, page={page}"
            )
            return []

        try:
            items = self._parse_search_results(html)
        except Exception as e:
            logger.error(f"Jable.get_model_videos 解析失败: {e}")
            if self.strict_failures:
                raise SourceSearchError("jable_parse_failed") from e
            return []

        for item in items:
            metrics = dict(item.get("metrics") or {})
            metrics["model_slug"] = normalized_slug
            item["metrics"] = metrics
        self._set_cached_items(cache_key, items, ttl_seconds=self.cache_ttl_default)
        return items

    def discover_hot_items(
        self, page: int = 1, *, force_refresh: bool = False
    ) -> list[dict]:
        cache_key = self._build_cache_key("discover_hot", page=page)
        if not force_refresh:
            cached_items = self._get_cached_items(cache_key)
            if cached_items is not None:
                return cached_items

        referer = f"https://{self.domain}/hot/"
        merged_results: list[dict] = []
        seen_avids: set[str] = set()

        for sort_by in self.HOT_BOARD_SORTS:
            url = self._build_hot_board_url(sort_by=sort_by, page=page)
            for item in self._discover_results_from_url(
                url=url,
                referer=referer,
                source_label="hot_board",
                extra_metrics={"hot_board_sort": sort_by},
            ):
                avid = str(item.get("avid", "")).strip().upper()
                if not avid or avid in seen_avids:
                    continue
                seen_avids.add(avid)
                merged_results.append(item)

        if merged_results:
            self._set_cached_items(
                cache_key, merged_results, ttl_seconds=self.cache_ttl_hot
            )
            return merged_results

        logger.warning("Jable.hot_board 未获取到可用候选")
        return []

    def discover_latest_updates(
        self,
        page: int = 1,
        *,
        force_refresh: bool = False,
    ) -> list[dict]:
        cache_key = self._build_cache_key("discover_latest", page=page)
        if not force_refresh:
            cached_items = self._get_cached_items(cache_key)
            if cached_items is not None:
                return cached_items

        items = self._discover_results_from_url(
            url=self._build_listing_url("/latest-updates/", page=page),
            referer=f"https://{self.domain}/latest-updates/",
            source_label="latest_updates",
        )
        if items:
            self._set_cached_items(cache_key, items, ttl_seconds=self.cache_ttl_latest)
        return items

    def get_tag_videos(
        self,
        tag_slug: str,
        page: int = 1,
        *,
        force_refresh: bool = False,
    ) -> list[dict]:
        normalized_slug = self._normalize_taxonomy_slug(tag_slug, prefix="tags")
        if not normalized_slug:
            return []

        cache_key = self._build_cache_key(
            "tag_videos",
            slug=normalized_slug,
            page=page,
        )
        if not force_refresh:
            cached_items = self._get_cached_items(cache_key)
            if cached_items is not None:
                return cached_items

        path = f"/tags/{quote(normalized_slug)}/"
        url = self._build_listing_url(path, page=page)
        referer = f"https://{self.domain}{path}"
        html = self._request_html(
            url,
            referer=referer,
            validator=self._is_listing_page_html,
        )
        if not html:
            logger.warning(
                "Jable.get_tag_videos 获取 HTML 失败，当前返回空结果。"
                f" tag_slug={normalized_slug}, page={page}"
            )
            return []

        try:
            items = self._parse_search_results(html)
        except Exception as e:
            logger.error(f"Jable.get_tag_videos 解析失败: {e}")
            if self.strict_failures:
                raise SourceSearchError("jable_parse_failed") from e
            return []

        for item in items:
            metrics = dict(item.get("metrics") or {})
            metrics["tag_slug"] = normalized_slug
            item["metrics"] = metrics
        self._set_cached_items(cache_key, items, ttl_seconds=self.cache_ttl_default)
        return items

    def get_category_videos(
        self,
        category_slug: str,
        page: int = 1,
        *,
        force_refresh: bool = False,
    ) -> list[dict]:
        normalized_slug = self._normalize_taxonomy_slug(
            category_slug, prefix="categories"
        )
        if not normalized_slug:
            return []

        cache_key = self._build_cache_key(
            "category_videos",
            slug=normalized_slug,
            page=page,
        )
        if not force_refresh:
            cached_items = self._get_cached_items(cache_key)
            if cached_items is not None:
                return cached_items

        path = f"/categories/{quote(normalized_slug)}/"
        url = self._build_listing_url(path, page=page)
        referer = f"https://{self.domain}{path}"
        html = self._request_html(
            url,
            referer=referer,
            validator=self._is_listing_page_html,
        )
        if not html:
            logger.warning(
                "Jable.get_category_videos 获取 HTML 失败，当前返回空结果。"
                f" category_slug={normalized_slug}, page={page}"
            )
            return []

        try:
            items = self._parse_search_results(html)
        except Exception as e:
            logger.error(f"Jable.get_category_videos 解析失败: {e}")
            if self.strict_failures:
                raise SourceSearchError("jable_parse_failed") from e
            return []

        for item in items:
            metrics = dict(item.get("metrics") or {})
            metrics["category_slug"] = normalized_slug
            item["metrics"] = metrics
        self._set_cached_items(cache_key, items, ttl_seconds=self.cache_ttl_default)
        return items

    def _build_cache_key(self, kind: str, **kwargs) -> str:
        segments = [f"{name}={kwargs[name]}" for name in sorted(kwargs)]
        payload = "|".join(segments)
        scope = ""
        if self.credential_context is not None:
            import hashlib

            scope = (
                hashlib.sha256(self.credential_context.scope_key.encode()).hexdigest()
                + ":"
            )
        return f"jable:search:{self.domain}:{scope}{kind}:{payload}"

    def _get_cached_items(self, key: str) -> list[dict] | None:
        if not self.cache_enabled:
            return None
        cached_payload = cache.get(key)
        if not isinstance(cached_payload, list):
            return None
        return deepcopy(cached_payload)

    def _set_cached_items(
        self,
        key: str,
        payload: list[dict],
        *,
        ttl_seconds: int,
    ) -> None:
        if not self.cache_enabled:
            return

        def publish():
            cache.set(key, deepcopy(payload), timeout=max(int(ttl_seconds), 1))

        if self.credential_context is not None:
            self.credential_context.check()
        publish()  # Versioned namespace; no network while a DB fence is held.

    def _build_search_url(self, keyword: str, page: int = 1) -> str:
        encoded = quote(keyword.strip())
        if page <= 1:
            return f"https://{self.domain}/search/{encoded}/"
        return (
            f"https://{self.domain}/search/{encoded}/?"
            f"{urlencode({'from': self._format_page_token(page)})}"
        )

    def _build_model_videos_url(
        self,
        *,
        model_slug: str,
        page: int = 1,
        sort_by: str,
    ) -> str:
        query = {
            "mode": "async",
            "function": "get_block",
            "block_id": "list_videos_common_videos_list",
            "sort_by": sort_by,
        }
        if page > 1:
            query["from"] = self._format_page_token(page)
        return f"https://{self.domain}/models/{quote(model_slug)}/?{urlencode(query)}"

    def _discover_results_from_url(
        self,
        *,
        url: str,
        referer: str,
        source_label: str,
        extra_metrics: dict | None = None,
    ) -> list[dict]:
        html = self._request_html(
            url,
            referer=referer,
            validator=self._is_listing_page_html,
        )
        if not html:
            return []

        try:
            items = self._parse_search_results(html)
        except Exception as e:
            logger.error(f"Jable.{source_label} 解析失败: {e}. url={url}")
            if self.strict_failures:
                raise SourceSearchError("jable_parse_failed") from e
            return []

        if not items:
            return []

        for item in items:
            metrics = dict(item.get("metrics") or {})
            if extra_metrics:
                for key, value in extra_metrics.items():
                    if key not in metrics:
                        metrics[key] = value
            discovery_sources = list(metrics.get("discovery_sources") or [])
            if source_label not in discovery_sources:
                discovery_sources.append(source_label)
            metrics["discovery_sources"] = discovery_sources
            item["metrics"] = metrics
        return items

    def _request_html(
        self,
        url: str,
        *,
        referer: str,
        validator: Callable[[str], bool] | None = None,
        fetcher: PageFetchService | None = None,
        candidate_index: int = 1,
        request_id: str = "",
    ) -> str | None:
        active_fetcher = fetcher or self.page_fetcher.for_lookup()
        result = active_fetcher.fetch(
            url,
            direct_fetch=lambda: self.fetch_page(url, referer=referer),
            validator=validator or (lambda html: bool(html)),
            strategy=self.browser_fetch_strategy,
            source=self.get_source_name(),
            candidate_index=candidate_index,
            request_id=request_id,
            path_kind=(
                "detail"
                if "/videos/" in url
                else "search"
                if "/search/" in url
                else "listing"
            ),
            session_handler=self
            if self.requires_bound_page
            or (
                active_fetcher.session_reuse_enabled
                and self.proxy
                and getattr(active_fetcher.browser, "provider", None) == "byparr"
            )
            else None,
        )
        if not result.ok:
            self._request_state.listing_failure = result.failure
            if self.strict_failures:
                raise SourceSearchError(f"jable_fetch_{result.failure}")
        return result.html if result.ok else None

    def _is_detail_page_html(self, html: str) -> bool:
        return bool(re.search(r'var hlsUrl = ["\']([^"\']+)["\']', html))

    def _is_listing_page_html(self, html: str) -> bool:
        if "video-img-box" in html:
            return True
        lowered = html.lower()
        return "<form" in lowered and any(
            marker in lowered
            for marker in ("no results", "no videos", "沒有結果", "没有结果")
        )

    def _build_listing_url(self, path: str, *, page: int = 1) -> str:
        normalized_path = str(path or "/").strip() or "/"
        if not normalized_path.startswith("/"):
            normalized_path = f"/{normalized_path}"
        if page <= 1:
            return f"https://{self.domain}{normalized_path}"
        separator = "&" if "?" in normalized_path else "?"
        return (
            f"https://{self.domain}{normalized_path}{separator}"
            f"{urlencode({'from': self._format_page_token(page)})}"
        )

    def _normalize_model_slug(self, model_slug: str) -> str:
        normalized = str(model_slug or "").strip()
        if not normalized:
            return ""
        match = re.search(r"/models/([^/?#]+)/?", normalized)
        if match:
            normalized = match.group(1)
        return normalized.strip().strip("/").lower()

    def _normalize_taxonomy_slug(self, raw_slug: str, *, prefix: str) -> str:
        normalized = str(raw_slug or "").strip()
        if not normalized:
            return ""
        pattern = rf"/{re.escape(prefix)}/([^/?#]+)/?"
        match = re.search(pattern, normalized)
        if match:
            normalized = match.group(1)
        return normalized.strip().strip("/").lower()

    def _build_hot_board_url(self, *, sort_by: str, page: int = 1) -> str:
        query = {
            "mode": "async",
            "function": "get_block",
            "block_id": "list_videos_common_videos_list",
            "sort_by": sort_by,
        }
        if page > 1:
            query["from"] = self._format_page_token(page)
        return f"https://{self.domain}/hot/?{urlencode(query)}"

    def _format_page_token(self, page: int) -> str:
        return f"{max(int(page), 1):02d}"

    def _parse_search_results(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select("div.video-img-box")

        results: list[dict] = []
        for card in cards:
            title_link = card.select_one("h6.title a")
            image_link = card.select_one("div.img-box a")
            image = card.select_one("div.img-box img")
            subtitle = card.select_one("p.sub-title")
            duration_tag = card.select_one("div.absolute-bottom-right span.label")

            detail_url = ""
            title_href = self._get_tag_attr(title_link, "href")
            image_href = self._get_tag_attr(image_link, "href")
            if title_href:
                detail_url = urljoin(f"https://{self.domain}/", title_href)
            elif image_href:
                detail_url = urljoin(f"https://{self.domain}/", image_href)

            title = title_link.get_text(" ", strip=True) if title_link else ""
            cover_url = self._extract_cover_url(image)
            avid = self._extract_avid(title=title, detail_url=detail_url)
            if not avid:
                continue

            metrics = self._parse_metrics(subtitle)
            duration = duration_tag.get_text(strip=True) if duration_tag else ""
            if duration:
                metrics["duration"] = duration

            results.append(
                {
                    "avid": avid,
                    "title": title,
                    "detail_url": detail_url,
                    "cover_url": cover_url,
                    "source": self.get_source_name(),
                    "metrics": metrics,
                }
            )

        return results

    def _parse_video_detail(self, *, html: str, avid: str, detail_url: str) -> dict:
        soup = BeautifulSoup(html, "html.parser")
        info = self.parse_html(html)
        parsed_avid = str(getattr(info, "avid", "") or avid).strip().upper()
        title = str(getattr(info, "source_title", "") or "").strip()
        if not title:
            title_node = soup.select_one("h4.title, h1.title, title")
            title = title_node.get_text(" ", strip=True) if title_node else ""
            title = re.sub(r"\s*-\s*Jable\.TV.*$", "", title).strip()

        metadata = soup.select_one("section.video-info")
        if metadata is None:
            raise ValueError("Jable detail metadata section missing")
        actors = self._extract_detail_links(
            metadata, selector="div.models a.model[href]", prefer_tooltip=True
        )
        genres = self._extract_detail_links(
            metadata,
            selector='a[href*="/tags/"], a[href*="/categories/"]',
        )
        cover_url = self.get_cover_url(html) or ""

        payload = {
            "avid": parsed_avid,
            "title": title,
            "detail_url": detail_url,
            "cover_url": cover_url,
            "actors": [item["name"] for item in actors],
            "actor_slugs": [item["slug"] for item in actors if item.get("slug")],
            "genres": [item["name"] for item in genres],
            "genre_slugs": [item["slug"] for item in genres if item.get("slug")],
            "tag_slugs": [
                item["slug"]
                for item in genres
                if item.get("slug") and item.get("taxonomy") == "tag"
            ],
            "category_slugs": [
                item["slug"]
                for item in genres
                if item.get("slug") and item.get("taxonomy") == "category"
            ],
        }
        return {key: value for key, value in payload.items() if value not in ("", [])}

    def _extract_detail_links(
        self, soup, *, selector: str, prefer_tooltip: bool = False
    ) -> list[dict]:
        output: list[dict] = []
        seen: set[tuple[str, str]] = set()
        for anchor in soup.select(selector):
            name = anchor.get_text(" ", strip=True)
            if prefer_tooltip:
                for attr in ("data-original-title", "title", "alt"):
                    nodes = [anchor, *anchor.select(f"[{attr}]")]
                    full_name = next(
                        (
                            self._get_tag_attr(node, attr).strip()
                            for node in nodes
                            if self._get_tag_attr(node, attr).strip()
                        ),
                        "",
                    )
                    if full_name:
                        name = full_name
                        break
            href = self._get_tag_attr(anchor, "href")
            if not name:
                continue
            slug = ""
            taxonomy = ""
            match = re.search(r"/(?:models|tags|categories)/([^/?#]+)/?", href)
            if match:
                slug = match.group(1).strip().lower()
            taxonomy_match = re.search(r"/(tags|categories)/[^/?#]+/?", href)
            if taxonomy_match:
                taxonomy = (
                    "category" if taxonomy_match.group(1) == "categories" else "tag"
                )
            key = (name.casefold(), slug)
            if key in seen:
                continue
            seen.add(key)
            output.append({"name": name, "slug": slug, "taxonomy": taxonomy})
        return output

    def _extract_cover_url(self, image) -> str:
        if image is None:
            return ""

        for attr in ("data-src", "data-original", "src"):
            value = self._get_tag_attr(image, attr)
            if not value:
                continue
            if "placeholder" in value:
                continue
            return urljoin(f"https://{self.domain}/", value)
        return ""

    def _get_tag_attr(self, tag, attr_name: str) -> str:
        if tag is None:
            return ""

        value = tag.get(attr_name)
        if isinstance(value, str):
            return value.strip()
        return ""

    def _extract_avid(self, title: str, detail_url: str) -> str:
        title_match = re.match(r"^\s*([A-Za-z0-9]+-\d+(?:-[A-Za-z0-9]+)?)\b", title)
        if title_match:
            return title_match.group(1).upper()

        url_match = re.search(
            r"/videos/([a-z0-9]+-\d+(?:-[a-z0-9]+)?)/?$",
            detail_url,
            re.IGNORECASE,
        )
        if url_match:
            return url_match.group(1).upper()
        return ""

    def _parse_metrics(self, subtitle) -> dict:
        if subtitle is None:
            return {}

        text_nodes = [
            text.strip() for text in subtitle.stripped_strings if text.strip()
        ]
        if not text_nodes:
            return {}

        metrics: dict = {}
        if len(text_nodes) >= 2:
            metrics["views"] = self._parse_metric_number(text_nodes[0])
            metrics["likes"] = self._parse_metric_number(text_nodes[1])
            return metrics

        cleaned = " ".join(text_nodes)
        if not cleaned:
            return {}

        likes_match = re.search(r"(\d+)\s*$", cleaned)
        if likes_match:
            likes_text = likes_match.group(1)
            views_text = cleaned[: likes_match.start()].strip()
            if views_text:
                metrics["views"] = self._parse_metric_number(views_text)
            metrics["likes"] = self._parse_metric_number(likes_text)
            return metrics

        metrics["views"] = self._parse_metric_number(cleaned)
        return metrics

    def _parse_metric_number(self, raw: str) -> int:
        digits = re.sub(r"[^\d]", "", raw or "")
        return int(digits) if digits else 0
