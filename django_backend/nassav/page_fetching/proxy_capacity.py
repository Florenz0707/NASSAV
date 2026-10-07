"""Cross-worker, owner-fenced capacity for any configured proxy endpoint."""

import hashlib
import math
import time
from contextlib import contextmanager
from threading import Event, Thread
from uuid import uuid4

import redis

from .proxy_server import ProxyCapacityError

# Redis time avoids differing clocks across worker hosts. Each caller passes the
# same configured limit; lowering it blocks new entrants until holders drain.
_ACQUIRE = """
local t = redis.call('TIME')
local now = tonumber(t[1]) + tonumber(t[2]) / 1000000
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now)
if redis.call('ZCARD', KEYS[1]) >= tonumber(ARGV[2]) then return 0 end
redis.call('ZADD', KEYS[1], now + tonumber(ARGV[3]), ARGV[1])
redis.call('EXPIRE', KEYS[1], tonumber(ARGV[3]) * 2)
return 1
"""
_RENEW = """
local t = redis.call('TIME')
local now = tonumber(t[1]) + tonumber(t[2]) / 1000000
local expires = redis.call('ZSCORE', KEYS[1], ARGV[1])
if not expires or tonumber(expires) <= now then return 0 end
redis.call('ZADD', KEYS[1], now + tonumber(ARGV[2]), ARGV[1])
redis.call('EXPIRE', KEYS[1], tonumber(ARGV[2]) * 2)
return 1
"""


class RedisProxyCapacity:
    def __init__(self, client, endpoint: str, limit: int):
        self.client, self.limit = client, limit
        # Provider and target/proxy route intentionally do not partition one server.
        self.key = (
            "nassav:proxy:capacity:v1:"
            + hashlib.sha256(endpoint.rstrip("/").encode()).hexdigest()
        )

    @contextmanager
    def slot(self, timeout_ms: int, *, check):
        owner = uuid4().hex
        ttl = max(90, math.ceil(timeout_ms / 1000) + 30)
        wait_until = time.monotonic() + timeout_ms / 1000
        try:
            while True:
                check()
                if self.client.eval(_ACQUIRE, 1, self.key, owner, self.limit, ttl):
                    break
                if time.monotonic() >= wait_until:
                    raise ProxyCapacityError("Proxy server capacity wait timed out")
                time.sleep(0.05)
        except redis.RedisError as error:
            raise ProxyCapacityError("Proxy server capacity unavailable") from error

        stopped, lost = Event(), Event()

        def renew():
            while not stopped.wait(ttl / 3):
                try:
                    if not self.client.eval(_RENEW, 1, self.key, owner, ttl):
                        lost.set()
                        return
                except redis.RedisError:
                    lost.set()
                    return

        heartbeat = Thread(target=renew, daemon=True)
        heartbeat.start()
        try:
            check()
            yield
            if lost.is_set() or not self.client.eval(_RENEW, 1, self.key, owner, ttl):
                raise ProxyCapacityError("Proxy server capacity lease lost")
        except redis.RedisError as error:
            raise ProxyCapacityError("Proxy server capacity unavailable") from error
        finally:
            stopped.set()
            heartbeat.join(timeout=1)
            try:
                self.client.zrem(self.key, owner)
            except redis.RedisError:
                # TTL recovers only this holder; never erase another owner's slot.
                pass
