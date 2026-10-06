import time
from collections.abc import Callable, Mapping
from pathlib import Path

from django.conf import settings
from django.core.cache import cache
from loguru import logger

from nassav.composition import source_factories
from nassav.page_fetching.coordination import (
    refresh_key,
    session_refresh_coordinator,
)
from nassav.resource_contracts import SourceLookup
from nassav.scraper import AVDownloadInfo
from nassav.source.CookieRepository import (
    SourceCookieRecord,
    proxy_route_profile,
    source_cookie_repository,
)
from nassav.source.CookieRuntimeCache import source_cookie_runtime_cache
from nassav.source.SourceBase import SourceBase
from nassav.source.titles import normalize_source_title as normalize_source_title


class SourceManager(SourceLookup):
    """下载器管理器"""

    LOCAL_COOKIE_CACHE_TTL = 30.0

    def __init__(
        self,
        *,
        factories: Mapping[str, Callable[[], SourceBase]] | None = None,
        config: Mapping[str, dict] | None = None,
    ):
        proxy = settings.PROXY_URL if settings.PROXY_ENABLED else None
        self.sources: dict[str, SourceBase] = {}

        # 注册下载器，根据配置中的权重
        self._config = config
        source_config = config if config is not None else settings.SOURCE_CONFIG
        registered = (
            factories
            if factories is not None
            else source_factories(
                proxy, settings.BROWSER_FETCH_CONFIG, self.set_source_cookie
            )
        )
        for source_name, factory in registered.items():
            source_settings = source_config.get(source_name, {})
            weight = source_settings.get("weight")
            # 只有配置了有效权重的源才会被注册
            if weight:
                source = factory()
                self.sources[source.get_source_name()] = source

    def refresh_source_session(
        self, source_name: str, *, force: bool = False
    ) -> SourceCookieRecord | None:
        target = self.get_source(source_name)
        if target is None:
            return None

        shared = source_cookie_repository.get_cookie_record(source_name)
        local = source_cookie_runtime_cache.get_state(source_name)
        if (
            force
            or local is None
            or local.expires_at <= time.monotonic()
            or local.session != shared
        ):
            source_cookie_runtime_cache.set_state(
                source_name, shared, ttl_seconds=self.LOCAL_COOKIE_CACHE_TTL
            )
        target.set_session(shared)
        return shared

    def refresh_source_cookie(self, source_name: str, *, force: bool = False) -> str:
        """Legacy Cookie-only API backed by a complete session snapshot."""
        record = self.refresh_source_session(source_name, force=force)
        return record.cookie if record is not None else ""

    def set_runtime_source_cookie(
        self,
        source_name: str,
        cookie: str,
        *,
        updated_at: str | None = None,
    ) -> None:
        target = self.get_source(source_name)
        if target is None:
            return
        shared = source_cookie_repository.get_cookie_record(source_name)
        if (
            shared is not None
            and shared.cookie == cookie
            and (updated_at is None or shared.updated_at == updated_at)
        ):
            session = shared
        else:
            # A process-local legacy value cannot inherit a different row's UA.
            session = SourceCookieRecord(source_name.lower(), cookie)
        target.set_session(session)
        source_cookie_runtime_cache.set_state(
            source_name, session, ttl_seconds=self.LOCAL_COOKIE_CACHE_TTL
        )

    def auto_source_cookie(self, source_name: str) -> bool:
        """Coordinate the old Cookie API with page refreshes across processes."""
        source = self.get_source(source_name)
        if source is None:
            return False
        route = proxy_route_profile(source.proxy) or "unknown"
        key = refresh_key(source.get_source_name(), source.get_home_url(), route)
        previous = source_cookie_repository.get_cookie_record(source_name)
        baseline = previous.updated_at if previous is not None else None
        timeout_ms = getattr(getattr(source, "page_fetcher", None), "timeout_ms", 60000)
        coordinator = session_refresh_coordinator
        lease, busy_owner = coordinator.acquire(key, timeout_ms)
        if lease is None:
            if not busy_owner:
                return False
            record = coordinator.wait_for_session(
                key,
                busy_owner,
                baseline,
                route,
                lambda: source_cookie_repository.get_cookie_record(source_name),
                timeout_ms,
                require_reusable=False,
            )
            if record is None:
                return False
            self.set_runtime_source_cookie(
                source_name, record.cookie, updated_at=record.updated_at
            )
            return True
        outcome = "unusable"
        try:
            current = source_cookie_repository.get_cookie_record(source_name)
            if (
                current is not None
                and current.updated_at != baseline
                and current.cookie
            ):
                self.set_runtime_source_cookie(
                    source_name, current.cookie, updated_at=current.updated_at
                )
                outcome = "reused"
                return True
            success = source.set_cookie_auto(
                force_refresh=True, write_guard=lease.owned
            )
            if not success:
                return False
            saved = source_cookie_repository.get_cookie_record(source_name)
            if saved is None or not saved.cookie:
                return False
            self.set_runtime_source_cookie(
                source_name, saved.cookie, updated_at=saved.updated_at
            )
            outcome = "reused"
            return True
        finally:
            lease.close(outcome)

    def invalidate_source_cookie_cache(self, source_name: str) -> None:
        source_cookie_runtime_cache.invalidate(source_name)
        source_cookie_repository.invalidate_cookie(source_name)

    def set_source_cookie(
        self, source_name: str, cookie: str, *, user_agent: str | None = None
    ) -> bool:
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

        if not actual_name:
            return False

        # 更新内存中的 cookie
        try:
            record = source_cookie_repository.set_cookie(
                actual_name, cookie, user_agent=user_agent
            )
            target_source.set_session(record)
            source_cookie_runtime_cache.set_state(
                actual_name, record, ttl_seconds=self.LOCAL_COOKIE_CACHE_TTL
            )
            logger.info(f"已设置 {actual_name} 的 Cookie")
            return True
        except Exception as e:
            logger.error(f"保存 Cookie 到数据库失败: {e}")
            return False

    def get_sorted_sources(self) -> list[tuple[str, SourceBase]]:
        """获取按权重排序的下载器列表"""
        source_config = (
            self._config if self._config is not None else settings.SOURCE_CONFIG
        )
        sorted_items = []
        for name, downloader in self.sources.items():
            weight = source_config.get(name.lower(), {}).get("weight", 0)
            sorted_items.append((name, downloader, weight))
        sorted_items.sort(key=lambda x: x[2], reverse=True)
        return [(name, dl) for name, dl, _ in sorted_items]

    def get_info_from_any_source(
        self, avid: str
    ) -> tuple[
        AVDownloadInfo | None,
        SourceBase | None,
        str | None,
        dict[str, int | str | None],
    ]:
        """
        遍历所有源获取信息
        返回: (info, source, html, errors)
        errors: dict mapping source_name -> error_code (or error string)

        使用缓存提高性能，减少外部请求
        """
        import time

        avid_upper = avid.upper()
        cache_key = f"source_info:{avid_upper}"

        # 尝试从缓存获取
        cached_data = cache.get(cache_key)
        if cached_data:
            logger.info(f"从缓存获取 {avid_upper} 的信息")
            try:
                # 反序列化缓存数据
                info_dict = cached_data.get("info")
                source_name = cached_data.get("source_name")
                html = cached_data.get("html")
                errors = cached_data.get("errors", {})

                # 重建 AVDownloadInfo 对象
                if info_dict:
                    source = self.sources.get(source_name)
                    source_title = info_dict.get("source_title", "")
                    if not source_title and html and source is not None:
                        try:
                            repaired_info = source.parse_html(html)
                            if repaired_info is not None:
                                source_title = repaired_info.source_title
                        except Exception as e:
                            logger.warning(f"缓存 source_title 修复失败: {e}")

                    info = AVDownloadInfo(
                        avid=info_dict.get("avid", ""),
                        title=info_dict.get("title", ""),
                        m3u8=info_dict.get("m3u8", ""),
                        source_title=source_title,
                        source=info_dict.get("source", ""),
                        duration=info_dict.get("duration", ""),
                    )
                    return info, source, html, errors
            except Exception as e:
                logger.warning(f"缓存数据反序列化失败: {e}")
                # 缓存损坏，删除并继续正常流程
                cache.delete(cache_key)

        errors: dict[str, int | str | None] = {}

        for name, source in self.get_sorted_sources():
            self.refresh_source_cookie(name)
            logger.info(f"尝试从 {name} 获取 {avid}")
            # 重置源上的上次错误码
            try:
                source.last_error_code = None
            except Exception:
                pass

            html = source.get_html(avid)
            time.sleep(0.5)

            # 如果 fetch_html 记录了错误码且未获取到 html，则把错误码记录下来
            try:
                err = getattr(source, "last_error_code", None)
                if not html and err is not None:
                    errors[name] = err
            except Exception:
                pass

            if html:
                info = source.parse_html(html)
                if info:
                    info.avid = avid_upper

                    # 缓存成功获取的信息
                    try:
                        cache_data = {
                            "info": {
                                "avid": info.avid,
                                "title": info.title,
                                "m3u8": info.m3u8,
                                "source_title": info.source_title,
                                "source": info.source,
                                "duration": info.duration,
                            },
                            "source_name": name,
                            "html": html,
                            "errors": errors,
                        }
                        cache.set(cache_key, cache_data, timeout=3600)  # 缓存1小时
                        logger.info(f"已缓存 {avid_upper} 的信息")
                    except Exception as e:
                        logger.warning(f"缓存数据失败: {e}")

                    return info, source, html, errors

        return None, None, None, errors

    def get_info_from_source(
        self, avid: str, source_str: str
    ) -> tuple[
        AVDownloadInfo | None,
        SourceBase | None,
        str | None,
        dict[str, int | str | None],
    ]:
        """
        从指定源获取信息
        返回: (info, source, html, errors)
        """
        errors: dict[str, int | str | None] = {}

        # 查找对应的下载器（不区分大小写）
        source = None
        for name, dl in self.sources.items():
            if name.lower() == source_str.lower():
                source = dl
                break

        if not source:
            logger.warning(f"未找到源 {source_str} 对应的下载器")
            return None, None, None, errors

        self.refresh_source_cookie(source.get_source_name())
        logger.info(f"从 {source_str} 刷新 {avid}")
        try:
            source.last_error_code = None
        except Exception:
            pass

        html = source.get_html(avid)
        try:
            err = getattr(source, "last_error_code", None)
            if not html and err is not None:
                errors[source_str] = err
        except Exception:
            pass

        if html:
            logger.info(f"成功从源 {source_str} 获取 html")
            info = source.parse_html(html)
            if info:
                info.avid = avid.upper()
                return info, source, html, errors

        logger.warning(f"从 {source_str} 获取 {avid} 失败")
        return None, None, None, errors

    def get_resource_dir(self, avid: str) -> Path:
        """确保新的资源子目录存在并返回资源根目录

        注意：新的布局将封面和视频分开保存在 COVER_DIR/VIDEO_DIR，
        该方法保持兼容性，确保相关目录存在。返回值为资源根目录。"""
        cover_dir = Path(settings.COVER_DIR)
        video_dir = Path(settings.VIDEO_DIR)
        cover_dir.mkdir(parents=True, exist_ok=True)
        video_dir.mkdir(parents=True, exist_ok=True)
        return Path(settings.RESOURCE_DIR)

    def get_sources(self) -> list[tuple[str, SourceBase]]:
        """Return a snapshot of enabled names and adapters in registration order."""
        return list(self.sources.items())

    def get_source(self, source_name: str) -> SourceBase | None:
        for name, source in self.sources.items():
            if name.lower() == source_name.lower():
                return source
        return None


source_manager = SourceManager()
