"""Ephemeral URI maps and atomic cross-process owner leases, with bounded TTL."""

import json
from contextlib import asynccontextmanager
from uuid import uuid4
import asyncio
from django.utils.crypto import salted_hmac
from .policy import PlaybackGatewayError

_REGISTER = """
if not redis.call('HEXISTS',KEYS[1],ARGV[1]) and redis.call('HLEN',KEYS[1])>=10000 then return 0 end
redis.call('HSET',KEYS[1],ARGV[1],ARGV[2]);redis.call('EXPIRE',KEYS[1],ARGV[3]);return 1
"""
_ACQUIRE = """
local t=redis.call('TIME');local now=tonumber(t[1])+tonumber(t[2])/1000000
for i=1,2 do
 redis.call('ZREMRANGEBYSCORE',KEYS[i],'-inf',now)
 if redis.call('ZCARD',KEYS[i])>=tonumber(ARGV[i+1]) then return 0 end
end
for i=1,2 do redis.call('ZADD',KEYS[i],now+45,ARGV[1]);redis.call('EXPIRE',KEYS[i],90) end
return 1
"""
_RENEW = """
local t=redis.call('TIME');local now=tonumber(t[1])+tonumber(t[2])/1000000
for i=1,2 do local expires=redis.call('ZSCORE',KEYS[i],ARGV[1]);if not expires or tonumber(expires)<=now then return 0 end end
for i=1,2 do redis.call('ZADD',KEYS[i],now+45,ARGV[1]);redis.call('EXPIRE',KEYS[i],90) end
return 1
"""
_RELEASE = "for i=1,2 do redis.call('ZREM',KEYS[i],ARGV[1]) end;return 1"


class RedisAssetRegistry:
    def __init__(self, client):
        self.client = client

    def key(self, session_id, generation):
        return f"nassav:playback:assets:{session_id}:{generation}"

    def register(self, session_id, generation, url, kind, depth, ttl):
        if depth > 8:
            raise PlaybackGatewayError("manifest_depth_exceeded", 422)
        payload = json.dumps(
            {"url": url, "kind": kind, "depth": depth}, separators=(",", ":")
        )
        asset_id = salted_hmac(
            "playback-asset", f"{session_id}:{generation}:{payload}"
        ).hexdigest()
        if not self.client.eval(
            _REGISTER,
            1,
            self.key(session_id, generation),
            asset_id,
            payload,
            max(1, min(14400, int(ttl))),
        ):
            raise PlaybackGatewayError("asset_limit_exceeded", 422)
        return asset_id

    def get(self, session_id, generation, asset_id):
        payload = self.client.hget(self.key(session_id, generation), asset_id)
        if not payload:
            raise PlaybackGatewayError("asset_expired", 410)
        return json.loads(payload)


class CapacityLease:
    def __init__(self, check, release):
        self.check, self.release = check, release

    def __call__(self):
        return self.check()


class RedisPlaybackCapacity:
    def __init__(self, client, global_limit=16):
        self.client, self.limit = client, global_limit

    @asynccontextmanager
    async def slot(self, session_id):
        owner = uuid4().hex
        keys = [
            "nassav:playback:capacity:global",
            f"nassav:playback:capacity:{session_id}",
        ]
        lost = asyncio.Event()
        try:
            acquired = await asyncio.to_thread(
                self.client.eval, _ACQUIRE, 2, *keys, owner, self.limit, 4
            )
            if not acquired:
                raise PlaybackGatewayError("playback_busy", 429)
        except PlaybackGatewayError:
            raise
        except Exception as error:
            raise PlaybackGatewayError("capacity_unavailable", 503) from error

        async def heartbeat():
            try:
                while True:
                    await asyncio.sleep(10)
                    if not await asyncio.to_thread(
                        self.client.eval, _RENEW, 2, *keys, owner
                    ):
                        lost.set()
                        return
            except asyncio.CancelledError:
                raise
            except Exception:
                lost.set()

        task = asyncio.create_task(heartbeat())

        def check():
            if lost.is_set():
                raise PlaybackGatewayError("capacity_lost", 503)

        released = False
        release_lock = asyncio.Lock()

        async def release():
            nonlocal released
            async with release_lock:
                if released:
                    return
                released = True
                lost.set()
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                try:
                    await asyncio.to_thread(self.client.eval, _RELEASE, 2, *keys, owner)
                except Exception:
                    pass

        try:
            yield CapacityLease(check, release)
        finally:
            await release()
