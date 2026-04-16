import re
from copy import deepcopy
from typing import Optional
from urllib.parse import quote, urlencode, urljoin

from bs4 import BeautifulSoup
from django.conf import settings
from django.core.cache import cache
from loguru import logger
from nassav.scraper.AVDownloadInfo import AVDownloadInfo
from nassav.source.SourceBase import SourceBase


class Jable(SourceBase):
    """Jable下载器"""

    HOT_BOARD_SORTS = [
        "video_viewed_today",
        "video_viewed_week",
        "video_viewed_month",
        "video_viewed",
    ]

    def __init__(self, proxy: Optional[str] = None, timeout: int = 15):
        super().__init__(proxy, timeout)
        source_config = settings.SOURCE_CONFIG.get("jable", {})
        self.domain = source_config.get("domain", "jable.tv")
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

    def get_html(self, avid: str) -> Optional[str]:
        urls = [
            f"https://{self.domain}/videos/{avid.lower()}/",
            f"https://{self.domain}/videos/{avid.lower()}v/",
            f"https://{self.domain}/videos/{avid.lower()}bf/",
            f"https://{self.domain}/videos/{avid.lower()}ntum/",
        ]
        for url in urls:
            result = self.fetch_html(
                url, referer=f"https://{self.domain}/search/{avid.lower()}"
            )
            if result:
                return result
        return None

    def parse_html(self, html: str) -> Optional[AVDownloadInfo]:
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

    def get_cover_url(self, html: str) -> Optional[str]:
        try:
            match = re.search(r'<meta property="og:image" content="([^"]+)"', html)
            if match:
                return match.group(1)
            return None
        except Exception as e:
            logger.error(f"封面URL提取失败: {e}")
            return None

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
        html = self.fetch_html(url, referer=referer)
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
        html = self.fetch_html(url, referer=referer)
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
        html = self.fetch_html(url, referer=referer)
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
        html = self.fetch_html(url, referer=referer)
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
        return f"jable:search:{self.domain}:{kind}:{payload}"

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
        cache.set(key, deepcopy(payload), timeout=max(int(ttl_seconds), 1))

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

    def _discover_listing(
        self,
        path_candidates: list[str],
        *,
        page: int,
        source_label: str,
    ) -> list[dict]:
        referer = f"https://{self.domain}/"
        for path in path_candidates:
            url = self._build_listing_url(path, page=page)
            html = self.fetch_html(url, referer=referer)
            if not html:
                continue

            try:
                items = self._parse_search_results(html)
            except Exception as e:
                logger.error(f"Jable.{source_label} 解析失败: {e}. url={url}")
                continue

            if not items:
                continue

            for item in items:
                metrics = dict(item.get("metrics") or {})
                discovery_sources = list(metrics.get("discovery_sources") or [])
                if source_label not in discovery_sources:
                    discovery_sources.append(source_label)
                metrics["discovery_sources"] = discovery_sources
                item["metrics"] = metrics
            return items

        logger.warning(f"Jable.{source_label} 未获取到可用候选")
        return []

    def _discover_results_from_url(
        self,
        *,
        url: str,
        referer: str,
        source_label: str,
        extra_metrics: dict | None = None,
    ) -> list[dict]:
        html = self.fetch_html(url, referer=referer)
        if not html:
            return []

        try:
            items = self._parse_search_results(html)
        except Exception as e:
            logger.error(f"Jable.{source_label} 解析失败: {e}. url={url}")
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
