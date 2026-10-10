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
