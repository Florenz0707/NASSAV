import asyncio
from uuid import uuid4
from unittest.mock import Mock
import pytest
from channels.testing import HttpCommunicator
from django.test import Client
from django_project.asgi import application
from nassav.playback import records
from nassav.http.playback_media import capability
from test_playback_gateway import make_gateway, Response
from nassav.playback.redis_state import RedisPlaybackCapacity
from test_session_lifecycle_contracts import isolated_redis as _isolated_redis

playback_redis = _isolated_redis
from nassav.playback.contracts import PlaybackDescriptor


@pytest.mark.django_db(transaction=True)
def test_asgi_media_authorization_range_and_cleanup(
    operator_user, resource_factory, settings, monkeypatch
):
    from nassav import composition

    settings.PLAYBACK_ENABLED = True
    settings.PROXY_ENABLED = False
    client = Client()
    client.force_login(operator_user)
    resource = resource_factory(source="Jable")
    row = records.submit(
        operator_user.pk, client.session.session_key, resource.avid, uuid4()
    )
    token = records.claim(row.pk)
    records.ready(
        token,
        PlaybackDescriptor(
            "https://media.example/v",
            "https://source.example/detail",
            "UA",
            "jable",
            None,
            None,
        ),
    )
    row.refresh_from_db()
    aid = "opaque"
    signed = capability(row.pk, row.generation, aid)
    gateway, transport, capacity, registry = make_gateway(
        Response(b"abcd", 206, {"content-range": "bytes 2-5/10", "content-length": "4"})
    )
    registry.get = Mock(
        return_value={
            "url": "https://media.example/s.ts",
            "kind": "segment",
            "depth": 1,
        }
    )
    registry.client = Mock()
    monkeypatch.setattr(composition, "build_playback_gateway", lambda: gateway)

    async def run():
        url = f"/nassav/api/playback-sessions/{row.pk}/assets/{aid}?cap={signed}"
        cookie = f"sessionid={client.session.session_key}".encode()
        anonymous = HttpCommunicator(
            application, "GET", url, headers=[(b"host", b"localhost")]
        )
        assert (await anonymous.get_response())["status"] == 401
        invalid = HttpCommunicator(
            application,
            "GET",
            url.replace(signed, "invalid"),
            headers=[(b"host", b"localhost"), (b"cookie", cookie)],
        )
        assert (await invalid.get_response())["status"] == 403
        communicator = HttpCommunicator(
            application,
            "GET",
            url,
            headers=[
                (b"host", b"localhost"),
                (b"cookie", cookie),
                (b"range", b"bytes=2-5"),
            ],
        )
        await communicator.send_input({"type": "http.request", "body": b""})
        response = await communicator.receive_output(5)
        assert response["status"] == 206
        body = bytearray()
        while True:
            event = await communicator.receive_output(5)
            body.extend(event.get("body", b""))
            if not event.get("more_body", False):
                break
        await communicator.wait(5)
        assert body == b"abcd"
        assert transport.closed and capacity.active == 0

    asyncio.run(run())


@pytest.mark.django_db(transaction=True)
def test_asgi_disconnect_releases_stream(
    operator_user, resource_factory, settings, monkeypatch, playback_redis
):
    from nassav import composition

    settings.PLAYBACK_ENABLED = True
    settings.PROXY_ENABLED = False
    client = Client()
    client.force_login(operator_user)
    key = client.session.session_key
    resource = resource_factory(source="Jable")
    row = records.submit(operator_user.pk, key, resource.avid, uuid4())
    records.ready(
        records.claim(row.pk),
        PlaybackDescriptor(
            "https://media.example/v",
            "https://source.example/detail",
            "UA",
            "jable",
            None,
            None,
        ),
    )
    row.refresh_from_db()

    class SlowResponse(Response):
        async def aiter_raw(self, chunk_size=16384):
            yield b"G" * 16384
            await asyncio.sleep(100)

    gateway, transport, _, registry = make_gateway(SlowResponse(b""))
    gateway.capacity = RedisPlaybackCapacity(playback_redis)
    registry.get = Mock(
        return_value={"url": "https://media.example/a", "kind": "segment", "depth": 1}
    )
    registry.client = Mock()
    monkeypatch.setattr(composition, "build_playback_gateway", lambda: gateway)

    async def run():
        url = f"/nassav/api/playback-sessions/{row.pk}/assets/opaque?cap={capability(row.pk, row.generation, 'opaque')}"
        c = HttpCommunicator(
            application,
            "GET",
            url,
            headers=[(b"host", b"localhost"), (b"cookie", f"sessionid={key}".encode())],
        )
        await c.send_input({"type": "http.request", "body": b""})
        assert (await c.receive_output(5))["status"] == 200
        assert (await c.receive_output(5))["body"]
        await c.send_input({"type": "http.disconnect"})
        await c.wait(5)
        assert transport.closed
        assert playback_redis.zcard("nassav:playback:capacity:global") == 0
        assert playback_redis.zcard(f"nassav:playback:capacity:{row.pk}") == 0

    asyncio.run(run())
