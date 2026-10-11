import asyncio
from contextlib import asynccontextmanager
from uuid import uuid4
import httpx
import pytest
from nassav.playback.contracts import PlaybackDescriptor
from nassav.playback.gateway import PlaybackGateway, range_header
from nassav.playback.manifest import parse_manifest
from nassav.playback.policy import TargetPolicy, PlaybackGatewayError
from nassav.playback.transport import HttpxPlaybackTransport


def policy():
    async def resolve(host):
        return ["93.184.216.34"]

    return TargetPolicy(["media.example"], resolve=resolve)


def test_manifest_preserves_signed_queries_iv_map_range_and_multitrack():
    data = b"""#EXTM3U
#EXT-X-KEY:METHOD=AES-128,URI="key?signature=a,b",IV=0x0123
#EXT-X-MAP:URI="init.mp4",BYTERANGE="100@0"
#EXTINF:4,
#EXT-X-BYTERANGE:50@100
seg.ts?token=private
#EXT-X-ENDLIST
"""
    parsed = parse_manifest(data, "https://media.example/dir/v.m3u8", policy())
    assert [r.kind for r in parsed.references] == ["key", "init", "segment"]
    assert parsed.references[0].url.endswith("key?signature=a,b")
    output = parsed.render(["/key/1", "/init/2", "/segment/3"])
    assert (
        b"private" not in output
        and b"IV=0x0123" in output
        and b"BYTERANGE:50@100" in output
    )
    master = parse_manifest(
        b'#EXTM3U\n#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="a",URI="audio.m3u8"\n#EXT-X-STREAM-INF:BANDWIDTH=100,CODECS="avc1,mp4a",AUDIO="a"\nv.m3u8\n',
        "https://media.example/master",
        policy(),
    )
    assert [r.kind for r in master.references] == ["manifest", "manifest"]


@pytest.mark.parametrize(
    "data",
    [
        b"<html>challenge</html>",
        b"#EXTM3U\n#EXTINF:4\ns.ts",
        b'#EXTM3U\n#EXT-X-KEY:METHOD=SAMPLE-AES,URI="k"\ns.ts\n#EXT-X-ENDLIST',
        b'#EXTM3U\n#EXT-X-UNKNOWN:URI="https://media.example/x"\ns.ts\n#EXT-X-ENDLIST',
        b'#EXTM3U\n#EXT-X-MAP:URI="a",URI="b"\ns.ts\n#EXT-X-ENDLIST',
    ],
)
def test_unsupported_manifest_fails_closed(data):
    with pytest.raises(PlaybackGatewayError):
        parse_manifest(data, "https://media.example/v", policy())


@pytest.mark.parametrize(
    "url",
    [
        "http://media.example/a",
        "https://media.example@127.0.0.1/a",
        "https://media.example:8080/a",
        "https://media.example/a#secret",
        "https://media.example\\@127.0.0.1/a",
        "https://evil.example/a",
        "https://media.example/a\nHost: x",
    ],
)
def test_target_rejection(url):
    with pytest.raises(PlaybackGatewayError):
        policy().validate(url)


def test_dns_rebinding_and_mixed_private_addresses_rejected():
    async def resolve(host):
        return ["93.184.216.34", "127.0.0.1"]

    with pytest.raises(PlaybackGatewayError):
        asyncio.run(
            TargetPolicy(["media.example"], resolve=resolve).target(
                "https://media.example/a"
            )
        )


class Registry:
    def __init__(self):
        self.items = []

    def register(self, *args):
        self.items.append(args)
        return str(len(self.items))


class Capacity:
    def __init__(self):
        self.active = 0

    @asynccontextmanager
    async def slot(self, session):
        self.active += 1
        from nassav.playback.redis_state import CapacityLease

        async def release():
            pass

        try:
            yield CapacityLease(lambda: None, release)
        finally:
            self.active -= 1


class Response:
    def __init__(self, body, status=200, headers=None):
        self.data = body
        self.status_code = status
        self.headers = headers or {}
        self.closed = False
        self.reads = 0

    async def aclose(self):
        self.closed = True

    async def aiter_raw(self, chunk_size=16384):
        for offset in range(0, len(self.data), chunk_size):
            self.reads += 1
            yield self.data[offset : offset + chunk_size]


class Transport:
    def __init__(self, response, wait=False):
        self.response = response
        self.wait = wait
        self.closed = False

    @asynccontextmanager
    async def open(self, url, headers, method="GET"):
        try:
            if self.wait:
                await asyncio.sleep(100)
            yield self.response, "https://media.example/dir/v.m3u8"
        finally:
            self.closed = True


def make_gateway(response):
    transport = Transport(response)
    capacity = Capacity()
    registry = Registry()
    return (
        PlaybackGateway(transport, policy(), registry, capacity),
        transport,
        capacity,
        registry,
    )


def test_gateway_rewrites_and_checks_key_and_error_media():
    async def run():
        async def check():
            pass

        d = PlaybackDescriptor(
            "https://media.example/v",
            "https://source.example/detail",
            "UA",
            "jable",
            None,
            None,
        )
        for kind, data in [
            ("manifest", b"#EXTM3U\n#EXTINF:4,\ns.ts?secret=a\n#EXT-X-ENDLIST"),
            ("key", b"1234567890123456"),
            ("segment", b"G" + b"x" * 40000),
        ]:
            gateway, t, c, r = make_gateway(Response(data))
            async with gateway.open(
                uuid4(),
                1,
                d,
                {"url": d.manifest_url, "kind": kind, "depth": 0},
                check=check,
                asset_url=lambda aid, kind: "/opaque/" + aid,
                ttl=10,
            ) as result:
                body = b"".join([chunk async for chunk in result.body])
                assert (
                    b"secret" not in body
                    and result.headers["Cache-Control"] == "no-store"
                )
            assert t.closed and c.active == 0
        for kind, data in [("segment", b"<html>challenge"), ("key", b"bad")]:
            gateway, t, c, r = make_gateway(Response(data))
            with pytest.raises(PlaybackGatewayError):
                async with gateway.open(
                    uuid4(),
                    1,
                    d,
                    {"url": d.manifest_url, "kind": kind, "depth": 0},
                    check=check,
                    asset_url=lambda aid, kind: "/opaque/" + aid,
                    ttl=10,
                ):
                    pass
            assert t.closed and c.active == 0

    asyncio.run(run())


def test_upstream_range_preserved_and_invalid_range_rejected():
    async def run():
        async def check():
            pass

        d = PlaybackDescriptor(
            "https://media.example/v",
            "https://source.example/detail",
            "UA",
            "jable",
            None,
            None,
        )
        gateway, t, c, r = make_gateway(
            Response(
                b"abcd", 206, {"content-range": "bytes 2-5/10", "content-length": "4"}
            )
        )
        async with gateway.open(
            uuid4(),
            1,
            d,
            {"url": d.manifest_url, "kind": "segment", "depth": 0},
            check=check,
            asset_url=lambda aid, kind: aid,
            ttl=10,
            range_value="bytes=2-5",
        ) as result:
            assert (
                result.status == 206
                and result.headers["Content-Range"] == "bytes 2-5/10"
            )
            assert b"".join([x async for x in result.body]) == b"abcd"

    asyncio.run(run())
    for value in ["bytes=5-2", "bytes=1-2,3-4", "bytes=-", "garbage"]:
        with pytest.raises(PlaybackGatewayError):
            range_header(value)


def test_cancellation_closes_pending_transport_and_capacity():
    async def run():
        async def check():
            pass

        d = PlaybackDescriptor(
            "https://media.example/v",
            "https://source.example/detail",
            "UA",
            "jable",
            None,
            None,
        )
        gateway, t, c, r = make_gateway(Response(b"G"))
        t.wait = True

        async def request():
            async with gateway.open(
                uuid4(),
                1,
                d,
                {"url": d.manifest_url, "kind": "segment", "depth": 0},
                check=check,
                asset_url=lambda a, k: a,
                ttl=10,
            ):
                pass

        task = asyncio.create_task(request())
        await asyncio.sleep(0.03)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert t.closed and c.active == 0

    asyncio.run(run())


def test_slow_consumer_reads_on_demand_and_closes():
    async def run():
        async def check():
            pass

        response = Response(b"G" + b"x" * (8 * 1024 * 1024))
        gateway, t, c, r = make_gateway(response)
        d = PlaybackDescriptor(
            "https://media.example/v",
            "https://source.example/detail",
            "UA",
            "jable",
            None,
            None,
        )
        async with gateway.open(
            uuid4(),
            1,
            d,
            {"url": d.manifest_url, "kind": "segment", "depth": 0},
            check=check,
            asset_url=lambda a, k: a,
            ttl=10,
        ) as result:
            await anext(result.body)
            await asyncio.sleep(0.05)
            assert response.reads == 1
        assert t.closed and c.active == 0

    asyncio.run(run())


def test_httpx_pins_direct_target_sni_and_checks_redirects():
    async def run():
        requests = []

        def handler(request):
            requests.append(request)
            if len(requests) == 1:
                return httpx.Response(
                    302, headers={"location": "https://127.0.0.1/private"}
                )
            return httpx.Response(200, content=b"body")

        def factory(**kwargs):
            return httpx.AsyncClient(
                transport=httpx.MockTransport(handler), trust_env=False
            )

        transport = HttpxPlaybackTransport(policy(), client_factory=factory)
        with pytest.raises(PlaybackGatewayError):
            async with transport.open("https://media.example/a", {}):
                pass
        assert len(requests) == 1 and requests[0].url.host == "93.184.216.34"
        assert (
            requests[0].headers["host"] == "media.example"
            and requests[0].extensions["sni_hostname"] == "media.example"
        )
        assert "cookie" not in requests[0].headers
        with pytest.raises(PlaybackGatewayError):
            async with HttpxPlaybackTransport(
                policy(), "http://proxy.example", client_factory=factory
            ).open("https://media.example/a", {}):
                pass

    asyncio.run(run())


def test_session_close_during_idle_consumer_closes_upstream():
    async def run():
        stopped = False

        async def check():
            if stopped:
                raise PlaybackGatewayError("session_closed", 410)

        response = Response(b"G" + b"x" * 65536)
        gateway, t, c, r = make_gateway(response)
        d = PlaybackDescriptor(
            "https://media.example/v",
            "https://source.example/detail",
            "UA",
            "jable",
            None,
            None,
        )
        async with gateway.open(
            uuid4(),
            1,
            d,
            {"url": d.manifest_url, "kind": "segment", "depth": 0},
            check=check,
            asset_url=lambda a, k: a,
            ttl=10,
        ) as result:
            await anext(result.body)
            stopped = True
            await asyncio.sleep(0.6)
            assert response.closed
            with pytest.raises(PlaybackGatewayError):
                await anext(result.body)
        assert t.closed and c.active == 0

    asyncio.run(run())


def test_fmp4_init_and_relative_segment_are_registered():
    parsed = parse_manifest(
        b'#EXTM3U\n#EXT-X-MAP:URI="init.mp4"\n#EXTINF:4,\npart.m4s\n#EXT-X-ENDLIST',
        "https://media.example/movie/v.m3u8",
        policy(),
    )
    assert [r.kind for r in parsed.references] == ["init", "segment"]
    assert b"init.mp4" not in parsed.render(["/init", "/segment"])


def test_access_log_redacts_only_media_capabilities():
    from logging import LogRecord
    from nassav.playback.access_log import PlaybackAccessFilter

    record = LogRecord(
        "uvicorn.access",
        20,
        "",
        0,
        '%s - "%s %s HTTP/%s" %d',
        (
            "client",
            "GET",
            "/nassav/api/playback-sessions/s/assets/a?cap=secret",
            "1.1",
            200,
        ),
        None,
    )
    assert PlaybackAccessFilter().filter(record)
    assert "secret" not in record.getMessage()


def test_redirect_cookie_is_never_forwarded():
    import httpx
    from nassav.playback.transport import HttpxPlaybackTransport

    async def run():
        requests = []

        def handler(request):
            requests.append(request)
            if len(requests) == 1:
                return httpx.Response(
                    302,
                    headers={
                        "Location": "/second",
                        "Set-Cookie": "secret=private; Path=/",
                    },
                )
            return httpx.Response(200, content=b"media")

        async def resolve(host):
            return ["93.184.216.34"]

        def factory(**kwargs):
            return httpx.AsyncClient(transport=httpx.MockTransport(handler), **kwargs)

        transport = HttpxPlaybackTransport(
            TargetPolicy(["media.example"], resolve=resolve), client_factory=factory
        )
        async with transport.open("https://media.example/first", {}):
            pass
        assert len(requests) == 2
        assert all("cookie" not in request.headers for request in requests)

    asyncio.run(run())


@pytest.mark.parametrize(
    "kind,body",
    [("manifest", b"#EXTM3U\n#EXTINF:4,\ns.ts\n#EXT-X-ENDLIST\n"), ("key", b"k" * 16)],
)
def test_native_player_range_probe_on_full_small_representation(kind, body):
    async def run():
        gateway, transport, capacity, _ = make_gateway(Response(body))

        async def check():
            pass

        async with gateway.open(
            uuid4(),
            1,
            PlaybackDescriptor(
                "https://media.example/v.m3u8",
                "https://source.example/detail",
                "ua",
                "jable",
                None,
                None,
            ),
            {"url": "https://media.example/v.m3u8", "kind": kind, "depth": 0},
            check=check,
            asset_url=lambda aid, _kind: "/opaque/" + aid,
            ttl=30,
            range_value="bytes=0-",
        ) as result:
            assert result.status == 200 and "Content-Range" not in result.headers
            content = b"".join([chunk async for chunk in result.body])
            assert content and len(content) == int(result.headers["Content-Length"])
            if kind == "manifest":
                assert b"/opaque/" in content
            else:
                assert content == body
        assert transport.closed and capacity.active == 0

    asyncio.run(run())
