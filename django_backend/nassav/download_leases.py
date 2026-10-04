"""Execution-scoped download ownership, fenced mutations and bounded renewal."""

from nassav.download_contracts import (
    DownloadLeaseLost,
    DownloadOwnership,
)

from contextlib import contextmanager
from contextvars import ContextVar
from collections.abc import Callable
from threading import Event, Thread, RLock
from uuid import uuid4

import redis


_OWNED = "for i=1,#KEYS do if redis.call('get',KEYS[i]) ~= ARGV[1] then return 0 end end; return 1"
_RENEW = "for i=1,#KEYS do if redis.call('get',KEYS[i]) ~= ARGV[1] then return 0 end end; for i=1,#KEYS do redis.call('expire',KEYS[i],ARGV[2]) end; return 1"
_RELEASE = "if redis.call('get',KEYS[1]) == ARGV[1] then return redis.call('del',KEYS[1]) end; return 0"
_MUTATE = """
if redis.call('get',KEYS[1]) ~= ARGV[1] then return 0 end
local op = ARGV[2]
if (op == 'progress' or op == 'state') and ARGV[6] == '1' and redis.call('get',KEYS[4]) ~= ARGV[1] then return 0 end
if op == 'progress' then redis.call('setex',KEYS[2],3600,ARGV[3])
elseif op == 'remove_progress' then redis.call('del',KEYS[2])
elseif op == 'remove_queue' then redis.call('hdel',KEYS[3],ARGV[4])
elseif op == 'state' then
 local data = redis.call('hget',KEYS[3],ARGV[4])
 if data then local row = cjson.decode(data); row.state = ARGV[3]; row.updated_at = tonumber(ARGV[5]); redis.call('hset',KEYS[3],ARGV[4],cjson.encode(row)) end
elseif op == 'cleanup' then
 redis.call('del',KEYS[2]); redis.call('hdel',KEYS[3],ARGV[4]); redis.call('del',KEYS[1])
else return redis.error_reply('Unknown download mutation') end
return 1
"""


class DownloadLease(DownloadOwnership):
    GLOBAL_KEY = "nassav:global_download_lock"

    def __init__(
        self,
        avid: str,
        client_factory: Callable[[], redis.Redis],
        *,
        ttl: int = 3600,
        heartbeat_seconds: float | None = None,
    ):
        self.avid = avid.upper()
        self.owner = uuid4().hex
        self.task_key = f"nassav:task_lock:{self.avid}"
        self.client_factory = client_factory
        self.ttl = ttl
        self.global_ttl = ttl
        self.interval = (
            heartbeat_seconds if heartbeat_seconds is not None else min(1.0, ttl / 3)
        )
        self._state_lock = RLock()
        self.started = False
        self.global_held = False
        self._lost = Event()
        self._stop = Event()
        self._thread: Thread | None = None

    def start(self, ttl: int | None = None) -> None:
        if ttl is not None:
            self.ttl = ttl
            self.interval = min(self.interval, ttl / 3)
        try:
            acquired = self.client_factory().set(
                self.task_key, self.owner, nx=True, ex=self.ttl
            )
        except redis.RedisError as error:
            self._lost.set()
            raise DownloadLeaseLost("无法获取下载任务租约") from error
        if not acquired:
            self._lost.set()
            raise DownloadLeaseLost("同一资源的另一个下载任务持有租约")
        self.started = True
        self._thread = Thread(target=self._heartbeat, daemon=True)
        self._thread.start()

    def acquire_global(self, ttl: int = 3600) -> bool:
        with self._state_lock:
            self.check()
            try:
                acquired = bool(
                    self.client_factory().set(
                        self.GLOBAL_KEY, self.owner, nx=True, ex=ttl
                    )
                )
            except redis.RedisError as error:
                self._lost.set()
                raise DownloadLeaseLost("获取全局下载租约失败") from error
            if acquired:
                self.global_ttl = ttl
                self.global_held = True
            return acquired

    def _keys(self) -> list[str]:
        return [self.task_key] + ([self.GLOBAL_KEY] if self.global_held else [])

    def check(self) -> None:
        if self._lost.is_set():
            raise DownloadLeaseLost("下载租约已丢失")
        if not self.started:
            return  # Unused transport binding; no storage side effects.
        try:
            keys = self._keys()
            owned = self.client_factory().eval(_OWNED, len(keys), *keys, self.owner)
        except redis.RedisError:
            owned = False
        if not owned:
            self._lost.set()
            raise DownloadLeaseLost("下载租约已丢失")

    def cancelled(self) -> bool:
        return self._lost.is_set()

    def renew(self) -> bool:
        with self._state_lock:
            try:
                keys = self._keys()
                # Keep each configured TTL; validate both before extending either.
                client = self.client_factory()
                script = (
                    _RENEW
                    if not self.global_held
                    else "if redis.call('get',KEYS[1]) ~= ARGV[1] or redis.call('get',KEYS[2]) ~= ARGV[1] then return 0 end; redis.call('expire',KEYS[1],ARGV[2]); redis.call('expire',KEYS[2],ARGV[3]); return 1"
                )
                result = bool(
                    client.eval(
                        script, len(keys), *keys, self.owner, self.ttl, self.global_ttl
                    )
                )
            except redis.RedisError:
                result = False
            if not result:
                self._lost.set()
            return result

    def _heartbeat(self) -> None:
        while not self._stop.wait(self.interval):
            if not self.renew():
                return

    def release_global(self) -> bool:
        with self._state_lock:
            if not self.global_held:
                return False
            try:
                return bool(
                    self.client_factory().eval(_RELEASE, 1, self.GLOBAL_KEY, self.owner)
                )
            finally:
                self.global_held = False

    def mutate(self, operation: str, payload: str = "") -> bool:
        import time

        if not self.started:
            return False
        return bool(
            self.client_factory().eval(
                _MUTATE,
                4,
                self.task_key,
                f"nassav:task_progress:{self.avid}",
                "nassav:task_queue",
                self.GLOBAL_KEY,
                self.owner,
                operation,
                payload,
                self.avid,
                time.time(),
                "1" if self.global_held else "0",
            )
        )

    def close(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        if not self.started:
            return
        # Each cleanup is fenced and independent; a failed release cannot skip
        # task/progress cleanup or delete another execution's state.
        for cleanup in (self.release_global, lambda: self.mutate("cleanup")):
            try:
                cleanup()
            except redis.RedisError:
                pass


_current: ContextVar[DownloadOwnership | None] = ContextVar(
    "download_ownership", default=None
)


@contextmanager
def download_ownership(lease: DownloadOwnership):
    token = _current.set(lease)
    try:
        yield lease
    finally:
        try:
            lease.close()
        finally:
            _current.reset(token)


def current_download_ownership() -> DownloadOwnership | None:
    return _current.get()
