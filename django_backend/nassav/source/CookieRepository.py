from dataclasses import dataclass

from django.core.cache import cache


@dataclass
class SourceCookieRecord:
    source_name: str
    cookie: str
    updated_at: str | None = None


class SourceCookieRepository:
    CACHE_TIMEOUT = 3600

    def get_cookie(self, source_name: str) -> str:
        record = self.get_cookie_record(source_name)
        return record.cookie if record is not None else ""

    def get_cookie_record(self, source_name: str) -> SourceCookieRecord | None:
        from nassav.models import SourceCookie

        normalized = self.normalize_source_name(source_name)
        cache_key = self._cache_key(normalized)
        cached = cache.get(cache_key)
        if isinstance(cached, dict):
            return SourceCookieRecord(
                source_name=normalized,
                cookie=str(cached.get("cookie", "")),
                updated_at=cached.get("updated_at"),
            )

        cookie_obj = (
            SourceCookie.objects.filter(source_name__iexact=normalized)
            .order_by("-updated_at")
            .first()
        )
        if cookie_obj is None:
            cache.set(
                cache_key,
                {
                    "cookie": "",
                    "updated_at": None,
                },
                timeout=self.CACHE_TIMEOUT,
            )
            return None

        record = SourceCookieRecord(
            source_name=normalized,
            cookie=cookie_obj.cookie,
            updated_at=cookie_obj.updated_at.isoformat()
            if cookie_obj.updated_at
            else None,
        )
        cache.set(
            cache_key,
            {
                "cookie": record.cookie,
                "updated_at": record.updated_at,
            },
            timeout=self.CACHE_TIMEOUT,
        )
        return record

    def set_cookie(self, source_name: str, cookie: str) -> SourceCookieRecord:
        from nassav.models import SourceCookie

        normalized = self.normalize_source_name(source_name)
        cookie_obj, _ = SourceCookie.objects.update_or_create(
            source_name=normalized,
            defaults={"cookie": cookie},
        )
        record = SourceCookieRecord(
            source_name=normalized,
            cookie=cookie_obj.cookie,
            updated_at=cookie_obj.updated_at.isoformat()
            if cookie_obj.updated_at
            else None,
        )
        cache.set(
            self._cache_key(normalized),
            {
                "cookie": record.cookie,
                "updated_at": record.updated_at,
            },
            timeout=self.CACHE_TIMEOUT,
        )
        return record

    def invalidate_cookie(self, source_name: str) -> None:
        cache.delete(self._cache_key(self.normalize_source_name(source_name)))

    def normalize_source_name(self, source_name: str) -> str:
        return str(source_name).strip().lower()

    def _cache_key(self, source_name: str) -> str:
        return f"source_cookie:{source_name}"


source_cookie_repository = SourceCookieRepository()
