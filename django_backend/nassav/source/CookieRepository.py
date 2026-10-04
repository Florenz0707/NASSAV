"""Atomic, versioned SourceCookie snapshots and proxy-route identity."""

from abc import ABC, abstractmethod

import hashlib
import hmac
import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from urllib.parse import unquote, urlsplit

from django.conf import settings
from django.core.cache import cache
from django.db import IntegrityError, OperationalError, connection, transaction
from django.utils import timezone


@dataclass(frozen=True)
class SourceCookieRecord:
    source_name: str
    cookie: str = field(repr=False)
    updated_at: str | None = None
    user_agent: str | None = field(default=None, repr=False)
    expires_at: datetime | None = None
    egress_profile: str | None = field(default=None, repr=False)

    def usable_on_route(self, profile: str | None) -> bool:
        """Legacy records can try once; a known stale route or expiry cannot."""
        if self.expires_at is not None and self.expires_at <= timezone.now():
            return False
        return self.egress_profile is None or self.egress_profile == profile


def proxy_route_profile(proxy_url: str | None) -> str | None:
    """Key the configured route, including proxy identity, without storing it."""
    if not proxy_url:
        return None
    parsed = urlsplit(proxy_url)
    if parsed.scheme not in {"http", "https", "socks5"} or not parsed.hostname:
        raise ValueError("Invalid configured proxy route")
    host = parsed.hostname.lower()
    if host in {"localhost", "127.0.0.1", "::1"}:
        host = "local-proxy"
    default_port = {"http": 80, "https": 443, "socks5": 1080}[parsed.scheme]
    route = [
        parsed.scheme.lower(),
        host,
        parsed.port or default_port,
        unquote(parsed.username or ""),
        unquote(parsed.password or ""),
    ]
    payload = json.dumps(route, ensure_ascii=False, separators=(",", ":")).encode()
    return hmac.new(settings.SECRET_KEY.encode(), payload, hashlib.sha256).hexdigest()


class CookieRepository(ABC):
    """Complete snapshots, manual writes and version-fenced automatic writes."""

    @abstractmethod
    def get_cookie_record(self, source_name: str) -> SourceCookieRecord | None:
        raise NotImplementedError

    @abstractmethod
    def set_cookie(
        self, source_name: str, cookie: str, *, user_agent: str | None = None
    ) -> SourceCookieRecord:
        raise NotImplementedError

    @abstractmethod
    def set_session_if_version(
        self,
        source_name: str,
        *,
        expected_updated_at: str | None,
        cookie: str,
        user_agent: str,
        expires_at: datetime | None,
        egress_profile: str | None,
        write_guard: Callable[[], bool] | None = None,
    ) -> SourceCookieRecord | None:
        raise NotImplementedError

    @abstractmethod
    def set_automatic_cookie_if_version(
        self,
        source_name: str,
        *,
        expected_updated_at: str | None,
        cookie: str,
        write_guard: Callable[[], bool] | None = None,
    ) -> SourceCookieRecord | None:
        raise NotImplementedError

    @abstractmethod
    def invalidate_cookie(self, source_name: str) -> None:
        raise NotImplementedError


class SourceCookieRepository(CookieRepository):
    CACHE_TIMEOUT = 3600

    def get_cookie(self, source_name: str) -> str:
        record = self.get_cookie_record(source_name)
        return record.cookie if record is not None else ""

    def get_cookie_record(self, source_name: str) -> SourceCookieRecord | None:
        from nassav.models import SourceCookie

        normalized = self.normalize_source_name(source_name)
        # Check the database version before using shared cache. A late cache.set
        # from an older reader cannot make a newer session appear current.
        obj = (
            SourceCookie.objects.filter(source_name__iexact=normalized)
            .order_by("-updated_at")
            .first()
        )
        key = self._cache_key(normalized)
        if obj is None:
            cache.delete(key)
            return None
        version = obj.updated_at.isoformat()
        cached = cache.get(key)
        if (
            isinstance(cached, dict)
            and cached.get("updated_at") == version
            and {"cookie", "user_agent", "expires_at", "egress_profile"}
            <= cached.keys()
        ):
            return SourceCookieRecord(
                source_name=normalized,
                cookie=str(cached["cookie"]),
                updated_at=version,
                user_agent=cached["user_agent"],
                expires_at=(
                    datetime.fromisoformat(cached["expires_at"])
                    if cached["expires_at"]
                    else None
                ),
                egress_profile=cached["egress_profile"],
            )
        record = self._from_model(normalized, obj)
        cache.set(key, self._cache_payload(record), timeout=self.CACHE_TIMEOUT)
        return record

    def set_cookie(
        self, source_name: str, cookie: str, *, user_agent: str | None = None
    ) -> SourceCookieRecord:
        """Legacy/manual write; omitted UA clears all prior automatic metadata."""
        from nassav.models import SourceCookie

        normalized = self.normalize_source_name(source_name)
        values = {
            "cookie": cookie,
            "user_agent": (user_agent or None) if cookie else None,
            "expires_at": None,
            "egress_profile": None,
        }
        for attempt in range(5):
            try:
                with transaction.atomic():
                    obj = (
                        SourceCookie.objects.select_for_update()
                        .filter(source_name__iexact=normalized)
                        .first()
                    )
                    record = self._write_locked(normalized, obj, values)
                cache.delete(self._cache_key(normalized))
                return record
            except IntegrityError:
                if attempt == 4:
                    raise
            except OperationalError as error:
                self._retry_sqlite_lock(error, attempt)
        raise RuntimeError("Could not save source session")

    def set_session_if_version(
        self,
        source_name: str,
        *,
        expected_updated_at: str | None,
        cookie: str,
        user_agent: str,
        expires_at: datetime | None,
        egress_profile: str | None,
        write_guard: Callable[[], bool] | None = None,
    ) -> SourceCookieRecord | None:
        """Commit a verified browser session only if no newer write exists."""
        from nassav.models import SourceCookie

        if not cookie or not user_agent:
            raise ValueError("A reusable session requires Cookie and User-Agent")
        if not egress_profile:
            # The Byparr route has not been proven compatible with direct GET.
            return None
        normalized = self.normalize_source_name(source_name)
        values = {
            "cookie": cookie,
            "user_agent": user_agent,
            "expires_at": expires_at,
            "egress_profile": egress_profile,
        }
        for attempt in range(5):
            try:
                with transaction.atomic():
                    obj = (
                        SourceCookie.objects.select_for_update()
                        .filter(source_name__iexact=normalized)
                        .first()
                    )
                    actual = obj.updated_at.isoformat() if obj is not None else None
                    if actual != expected_updated_at or (
                        write_guard is not None and not write_guard()
                    ):
                        return None
                    if obj is not None and all(
                        getattr(obj, name) == value for name, value in values.items()
                    ):
                        return self._from_model(normalized, obj)
                    record = self._write_locked(normalized, obj, values)
                cache.delete(self._cache_key(normalized))
                return record
            except IntegrityError:
                if expected_updated_at is not None:
                    raise
                # Another writer created the absent row after our version check.
                return None
            except OperationalError as error:
                self._retry_sqlite_lock(error, attempt)
        raise RuntimeError("Could not save source session")

    def set_automatic_cookie_if_version(
        self,
        source_name: str,
        *,
        expected_updated_at: str | None,
        cookie: str,
        write_guard: Callable[[], bool] | None = None,
    ) -> SourceCookieRecord | None:
        """Legacy auto-cookie entrypoint, still fenced against manual writes."""
        from nassav.models import SourceCookie

        if not cookie:
            return None
        normalized = self.normalize_source_name(source_name)
        values = {
            "cookie": cookie,
            "user_agent": None,
            "expires_at": None,
            "egress_profile": None,
        }
        for attempt in range(5):
            try:
                with transaction.atomic():
                    obj = (
                        SourceCookie.objects.select_for_update()
                        .filter(source_name__iexact=normalized)
                        .first()
                    )
                    actual = obj.updated_at.isoformat() if obj is not None else None
                    if actual != expected_updated_at or (
                        write_guard is not None and not write_guard()
                    ):
                        return None
                    if obj is not None and all(
                        getattr(obj, name) == value for name, value in values.items()
                    ):
                        return self._from_model(normalized, obj)
                    record = self._write_locked(normalized, obj, values)
                cache.delete(self._cache_key(normalized))
                return record
            except IntegrityError:
                return None
            except OperationalError as error:
                self._retry_sqlite_lock(error, attempt)
        raise RuntimeError("Could not save automatic source Cookie")

    @staticmethod
    def _retry_sqlite_lock(error: OperationalError, attempt: int) -> None:
        if (
            connection.vendor != "sqlite"
            or "locked" not in str(error).lower()
            or attempt == 4
        ):
            raise error
        time.sleep(0.02 * (attempt + 1))

    def invalidate_cookie(self, source_name: str) -> None:
        cache.delete(self._cache_key(self.normalize_source_name(source_name)))

    @staticmethod
    def normalize_source_name(source_name: str) -> str:
        return str(source_name).strip().lower()

    @staticmethod
    def _cache_key(source_name: str) -> str:
        return f"source_cookie:{source_name}"

    @staticmethod
    def _cache_payload(record: SourceCookieRecord) -> dict:
        return {
            "cookie": record.cookie,
            "user_agent": record.user_agent,
            "expires_at": record.expires_at.isoformat() if record.expires_at else None,
            "egress_profile": record.egress_profile,
            "updated_at": record.updated_at,
        }

    @staticmethod
    def _from_model(source_name: str, obj) -> SourceCookieRecord:
        return SourceCookieRecord(
            source_name=source_name,
            cookie=obj.cookie,
            updated_at=obj.updated_at.isoformat(),
            user_agent=obj.user_agent,
            expires_at=obj.expires_at,
            egress_profile=obj.egress_profile,
        )

    def _write_locked(self, normalized: str, obj, values: dict) -> SourceCookieRecord:
        from nassav.models import SourceCookie

        if obj is None:
            obj = SourceCookie.objects.create(source_name=normalized, **values)
        else:
            changed_at = timezone.now()
            if changed_at <= obj.updated_at:
                changed_at = obj.updated_at + timedelta(microseconds=1)
            SourceCookie.objects.filter(pk=obj.pk).update(
                **values, updated_at=changed_at
            )
            for name, value in values.items():
                setattr(obj, name, value)
            obj.updated_at = changed_at
        return self._from_model(normalized, obj)


source_cookie_repository = SourceCookieRepository()
