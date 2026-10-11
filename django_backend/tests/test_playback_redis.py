from test_session_lifecycle_contracts import isolated_redis as _isolated_redis

playback_redis = _isolated_redis
import asyncio
from uuid import uuid4
import pytest
from nassav.playback.redis_state import RedisAssetRegistry, RedisPlaybackCapacity
from nassav.playback.policy import PlaybackGatewayError


def test_assets_are_session_generation_scoped_and_bounded(playback_redis):
    registry = RedisAssetRegistry(playback_redis)
    sid = uuid4()
    aid = registry.register(
        sid, 1, "https://media.example/v?token=secret", "manifest", 0, 30
    )
    assert "secret" not in aid and registry.get(sid, 1, aid)["kind"] == "manifest"
    with pytest.raises(PlaybackGatewayError):
        registry.get(sid, 2, aid)
    with pytest.raises(PlaybackGatewayError):
        registry.register(sid, 1, "https://media.example/a", "manifest", 9, 30)
    assert 0 < playback_redis.ttl(registry.key(sid, 1)) <= 30


def test_global_capacity_is_shared_and_owner_release_preserves_replacement(
    playback_redis,
):
    async def run():
        sid = uuid4()
        one = RedisPlaybackCapacity(playback_redis, 1)
        two = RedisPlaybackCapacity(playback_redis, 1)
        async with one.slot(sid):
            with pytest.raises(PlaybackGatewayError):
                async with two.slot(uuid4()):
                    pass
            key = "nassav:playback:capacity:global"
            playback_redis.delete(key)
            playback_redis.zadd(key, {"replacement": 9999999999})
        assert playback_redis.zscore(key, "replacement") == 9999999999

    asyncio.run(run())


def request_slot(socket_path, result):
    import redis

    async def run():
        client = redis.Redis(unix_socket_path=socket_path)
        try:
            async with RedisPlaybackCapacity(client, 1).slot(uuid4()):
                result.put("acquired")
        except PlaybackGatewayError:
            result.put("blocked")
        finally:
            client.close()

    asyncio.run(run())


def test_capacity_is_shared_with_separate_process(playback_redis):
    import multiprocessing

    async def run():
        context = multiprocessing.get_context("spawn")
        result = context.Queue()
        async with RedisPlaybackCapacity(playback_redis, 1).slot(uuid4()):
            process = context.Process(
                target=request_slot,
                args=(playback_redis.connection_pool.connection_kwargs["path"], result),
            )
            process.start()
            try:
                assert await asyncio.to_thread(result.get, True, 15) == "blocked"
                await asyncio.to_thread(process.join, 10)
                assert process.exitcode == 0
            finally:
                if process.is_alive():
                    process.terminate()
                    process.join(5)
                result.close()

    asyncio.run(run())


def test_cancelled_capacity_acquisition_releases_late_redis_owner(playback_redis):
    """A cancelled HTTP request cannot abandon its in-flight Redis thread."""
    from threading import Event
    from nassav.playback.redis_state import _ACQUIRE

    started, unblock, finished = Event(), Event(), Event()

    class DelayedAcquire:
        def eval(self, script, *args):
            if script == _ACQUIRE:
                started.set()
                assert unblock.wait(3)
                try:
                    return playback_redis.eval(script, *args)
                finally:
                    finished.set()
            return playback_redis.eval(script, *args)

    async def run():
        sid = uuid4()
        entered = False

        async def request():
            nonlocal entered
            async with RedisPlaybackCapacity(DelayedAcquire()).slot(sid):
                entered = True

        task = asyncio.create_task(request())
        try:
            assert await asyncio.to_thread(started.wait, 3)
            task.cancel()
            await asyncio.sleep(0)
            task.cancel()
        finally:
            unblock.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 3)
        assert await asyncio.to_thread(finished.wait, 3)
        assert not entered
        assert playback_redis.zcard("nassav:playback:capacity:global") == 0
        assert playback_redis.zcard(f"nassav:playback:capacity:{sid}") == 0

    asyncio.run(run())


def test_cancelled_explicit_release_still_finishes_cleanup(playback_redis, monkeypatch):
    import nassav.playback.redis_state as state

    async def run():
        original_sleep = asyncio.sleep
        started, stopping, finish = asyncio.Event(), asyncio.Event(), asyncio.Event()

        async def slow_heartbeat_sleep(seconds):
            if seconds != 10:
                return await original_sleep(seconds)
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                stopping.set()
                await finish.wait()

        monkeypatch.setattr(state.asyncio, "sleep", slow_heartbeat_sleep)
        sid = uuid4()
        async with RedisPlaybackCapacity(playback_redis).slot(sid) as lease:
            await asyncio.wait_for(started.wait(), 3)
            release = asyncio.create_task(lease.release())
            await asyncio.wait_for(stopping.wait(), 3)
            release.cancel()
            await original_sleep(0)
            release.cancel()
            finish.set()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(release, 3)
        assert playback_redis.zcard("nassav:playback:capacity:global") == 0
        assert playback_redis.zcard(f"nassav:playback:capacity:{sid}") == 0

    asyncio.run(run())


def test_ambiguous_acquisition_error_releases_only_own_lease(playback_redis):
    from nassav.playback.redis_state import _ACQUIRE

    class LostReply:
        def eval(self, script, *args):
            result = playback_redis.eval(script, *args)
            if script == _ACQUIRE:
                raise ConnectionError("reply lost after Redis commit")
            return result

    async def run():
        sid = uuid4()
        key = "nassav:playback:capacity:global"
        playback_redis.zadd(key, {"other-owner": 9999999999})
        with pytest.raises(PlaybackGatewayError, match="capacity_unavailable"):
            async with RedisPlaybackCapacity(LostReply()).slot(sid):
                pytest.fail("Unconfirmed acquisition cannot enter the slot")
        assert playback_redis.zrange(key, 0, -1) == [b"other-owner"]
        assert playback_redis.zcard(f"nassav:playback:capacity:{sid}") == 0

    asyncio.run(run())
