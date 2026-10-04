"""Bounded, owner-checked Redis coordination for one site's session refresh."""

from __future__ import annotations

from abc import ABC, abstractmethod

import math
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING
from threading import Event, Thread
from urllib.parse import urlsplit
from uuid import uuid4

import redis
from django.conf import settings

if TYPE_CHECKING:
    from nassav.source.CookieRepository import SourceCookieRecord

_RELEASE = "if redis.call('get', KEYS[1]) == ARGV[1] then redis.call('setex', KEYS[2], ARGV[2], ARGV[1] .. ':' .. ARGV[3]); return redis.call('del', KEYS[1]) else return 0 end"
_RENEW = "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('expire', KEYS[1], ARGV[2]) else return 0 end"


def lease_seconds(timeout_ms: int) -> int:
    # Byparr HTTP budget includes 5 s connect and 10 s control overhead;
    # leave room for the 3 s direct probe and cleanup.
    return max(90, math.ceil(timeout_ms / 1000) + 30)


def refresh_key(source_name: str, url: str, route_profile: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    if not host or not route_profile:
        raise ValueError("Session refresh requires a host and route profile")
    return (
        f"nassav:session:refresh:{source_name.strip().lower()}:{host}:{route_profile}"
    )


class RefreshStore(ABC):
    """Owner-fenced lease operations and short-lived refresh outcomes."""

    @abstractmethod
    def acquire(self, key: str, owner: str, ttl: int) -> tuple[bool, str | None]:
        raise NotImplementedError

    @abstractmethod
    def owner(self, key: str) -> str | None:
        raise NotImplementedError

    @abstractmethod
    def renew(self, key: str, owner: str, ttl: int) -> bool:
        raise NotImplementedError

    @abstractmethod
    def release(self, key: str, owner: str, outcome: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def outcome(self, key: str) -> str | None:
        raise NotImplementedError

    @abstractmethod
    def mark_unusable(self, key: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def recently_unusable(self, key: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def clear_unusable(self, key: str) -> None:
        raise NotImplementedError


class RedisRefreshStore(RefreshStore):
    def __init__(self, client: redis.Redis | None = None):
        self.client = (
            client if client is not None else redis.from_url(settings.CELERY_BROKER_URL)
        )

    @staticmethod
    def _decoded(value) -> str | None:
        return value.decode() if isinstance(value, bytes) else value

    def acquire(self, key: str, owner: str, ttl: int) -> tuple[bool, str | None]:
        if self.client.set(key, owner, nx=True, ex=ttl):
            return True, None
        return False, self._decoded(self.client.get(key))

    def owner(self, key: str) -> str | None:
        return self._decoded(self.client.get(key))

    def renew(self, key: str, owner: str, ttl: int) -> bool:
        return bool(self.client.eval(_RENEW, 1, key, owner, ttl))

    def release(self, key: str, owner: str, outcome: str) -> bool:
        return bool(
            self.client.eval(_RELEASE, 2, key, key + ":result", owner, 15, outcome)
        )

    def outcome(self, key: str) -> str | None:
        return self._decoded(self.client.get(key + ":result"))

    def mark_unusable(self, key: str) -> None:
        self.client.setex(key + ":unusable", 15, "1")

    def recently_unusable(self, key: str) -> bool:
        return bool(self.client.exists(key + ":unusable"))

    def clear_unusable(self, key: str) -> None:
        self.client.delete(key + ":unusable")


@dataclass
class RefreshLease:
    store: RefreshStore
    key: str
    owner: str
    ttl: int

    def __post_init__(self):
        self._stop = Event()
        self._lost = Event()
        self._heartbeat = Thread(target=self._renew_loop, daemon=True)
        self._heartbeat.start()

    def _renew_loop(self) -> None:
        while not self._stop.wait(max(1, self.ttl // 3)):
            try:
                if not self.store.renew(self.key, self.owner, self.ttl):
                    self._lost.set()
                    return
            except redis.RedisError:
                self._lost.set()
                return

    def owned(self) -> bool:
        if self._lost.is_set():
            return False
        try:
            held = self.store.owner(self.key) == self.owner
        except redis.RedisError:
            held = False
        if not held:
            self._lost.set()
        return held

    def close(self, outcome: str) -> None:
        self._stop.set()
        self._heartbeat.join(timeout=1)
        try:
            self.store.release(self.key, self.owner, outcome)
        except redis.RedisError:
            pass


class SessionRefreshCoordinator:
    def __init__(self, store: RefreshStore | None = None):
        self.store = store if store is not None else RedisRefreshStore()

    def acquire(
        self, key: str, timeout_ms: int
    ) -> tuple[RefreshLease | None, str | None]:
        """Return a lease, another owner, or neither when Redis is unavailable."""
        owner = uuid4().hex
        ttl = lease_seconds(timeout_ms)
        try:
            acquired, other_owner = self.store.acquire(key, owner, ttl)
        except redis.RedisError:
            return None, None
        return (
            (RefreshLease(self.store, key, owner, ttl), None)
            if acquired
            else (None, other_owner)
        )

    def wait_for_session(
        self,
        key: str,
        owner: str,
        baseline_version: str | None,
        route_profile: str,
        read_session,
        timeout_ms: int,
        *,
        require_reusable: bool = True,
    ) -> SourceCookieRecord | None:
        deadline = time.monotonic() + lease_seconds(timeout_ms) + 5
        delay = 0.05
        while time.monotonic() < deadline:
            try:
                current = read_session()
                if (
                    current is not None
                    and current.updated_at != baseline_version
                    and current.cookie
                    and (
                        not require_reusable
                        or (
                            current.user_agent
                            and current.egress_profile == route_profile
                            and current.usable_on_route(route_profile)
                        )
                    )
                ):
                    return current
                result = self.store.outcome(key)
                if result is not None and result.startswith(owner + ":"):
                    return None
                if self.store.owner(key) != owner:
                    return None
            except Exception:
                # A failed DB/cache read must not strand the page behind a lock.
                return None
            time.sleep(delay)
            delay = min(delay * 1.5, 0.5)
        return None


session_refresh_coordinator = SessionRefreshCoordinator()
