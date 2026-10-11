"""Browser-capable media stream must be bounded and killable before body EOF."""

import asyncio
import ssl
import time
import pytest
from nassav.playback.policy import TargetPolicy, PlaybackGatewayError


def test_browser_transport_rejects_untrusted_proxy_before_start():
    from nassav.playback.curl_transport import CurlPlaybackTransport

    async def run():
        transport = CurlPlaybackTransport(
            TargetPolicy(["media.example"]), "http://proxy.example:80"
        )
        with pytest.raises(PlaybackGatewayError, match="proxy_target_policy_required"):
            async with transport.open("https://media.example/v", {}):
                pass

    asyncio.run(run())


def test_browser_transport_real_tls_backpressure_and_cancel(tmp_path):
    from nassav.playback.curl_transport import CurlPlaybackTransport
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    from datetime import datetime, timedelta, timezone

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "media.example")])
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName("media.example")]), critical=False
        )
        .sign(key, hashes.SHA256())
    )
    ca = tmp_path / "ca.pem"
    private = tmp_path / "key.pem"
    sock = tmp_path / "tls.sock"
    ca.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    private.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(ca, private)

    async def run():
        received = {}
        finished = asyncio.Event()
        tasks = set()

        async def handler(reader, writer):
            task = asyncio.current_task()
            tasks.add(task)
            try:
                received["request"] = await reader.readuntil(b"\r\n\r\n")
                writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 16777216\r\n\r\n")
                for index in range(1024):
                    writer.write(b"G" * 16384)
                    await writer.drain()
                    received["sent"] = index + 1
            except (ConnectionError, ssl.SSLError):
                pass
            finally:
                writer.close()
                try:
                    await writer.wait_closed()
                except (ConnectionError, ssl.SSLError):
                    pass
                tasks.discard(task)
                finished.set()

        server = await asyncio.start_unix_server(handler, str(sock), ssl=context)

        async def resolve(host):
            return ["93.184.216.34"]

        transport = CurlPlaybackTransport(
            TargetPolicy(["media.example"], resolve=resolve),
            unix_socket_path=str(sock),
            cacert=str(ca),
        )
        try:
            async with transport.open(
                "https://media.example/video.ts", {"User-Agent": "fixture-UA"}
            ) as (response, final):
                assert response.status_code == 200
                assert len(await anext(response.aiter_raw(chunk_size=16384))) == 16384
                await asyncio.sleep(0.1)
                assert received["sent"] < 1024
                started = time.monotonic()
                await response.aclose()
                assert time.monotonic() - started < 2
            await asyncio.wait_for(finished.wait(), 2)
            assert b"Host: media.example" in received["request"]
            assert b"Cookie:" not in received["request"]
        finally:
            server.close()
            await server.wait_closed()
            for task in list(tasks):
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    asyncio.run(run())


def test_worker_uses_browser_profile_pins_dns_and_omits_cookies(monkeypatch):
    from io import BytesIO
    from curl_cffi.const import CurlOpt
    from nassav.playback import curl_worker

    recorded = {}

    class Curl:
        def __init__(self, **kwargs):
            pass

        def impersonate(self, profile, default_headers):
            recorded["profile"] = profile
            recorded["default_headers"] = default_headers
            return 0

        def setopt(self, key, value):
            recorded[key] = value

        def perform(self):
            for line in [
                b"HTTP/2 200\r\n",
                b"Content-Type: video/mp2t\r\n",
                b"Set-Cookie: private=secret\r\n",
                b"\r\n",
            ]:
                assert recorded[CurlOpt.HEADERFUNCTION](line) == len(line)
            assert recorded[CurlOpt.WRITEFUNCTION](b"G" * 100) == 100

        def close(self):
            recorded["closed"] = True

    monkeypatch.setattr(curl_worker, "Curl", Curl)
    output = BytesIO()
    curl_worker.transfer(
        {
            "url": "https://media.example/v",
            "proxy": None,
            "headers": {"User-Agent": "UA"},
            "method": "GET",
            "host": "media.example",
            "ip": "93.184.216.34",
            "impersonate": "chrome110",
        },
        output,
    )
    assert recorded["profile"] == "chrome110" and recorded["default_headers"] is False
    assert recorded[CurlOpt.RESOLVE] == [b"media.example:443:93.184.216.34"]
    assert recorded[CurlOpt.PROXY] == "" and recorded[CurlOpt.NOPROXY] == ""
    assert recorded[CurlOpt.FOLLOWLOCATION] == 0
    assert (
        recorded[CurlOpt.SSL_VERIFYPEER] == 1 and recorded[CurlOpt.SSL_VERIFYHOST] == 2
    )
    assert b"private" not in output.getvalue() and output.getvalue().endswith(
        b"G" * 100
    )
    assert recorded["closed"]


def test_bad_redirect_is_rejected_and_producer_closed():
    from nassav.playback.curl_transport import CurlPlaybackTransport
    from contextlib import asynccontextmanager
    from types import SimpleNamespace

    async def run():
        closed = []

        async def resolve(host):
            return ["93.184.216.34"]

        transport = CurlPlaybackTransport(
            TargetPolicy(["media.example"], resolve=resolve)
        )

        @asynccontextmanager
        async def single(url, headers, method):
            transport.policy.validate(url)
            try:
                yield SimpleNamespace(
                    status_code=302, headers={"location": "http://127.0.0.1/private"}
                )
            finally:
                closed.append(url)

        transport.single = single
        with pytest.raises(PlaybackGatewayError, match="target_rejected"):
            async with transport.open("https://media.example/v", {}):
                pass
        assert closed == ["https://media.example/v"]

    asyncio.run(run())


def test_cancellation_before_headers_kills_and_reaps_process(tmp_path):
    from nassav.playback.curl_transport import CurlPlaybackTransport
    import sys

    async def run():
        processes = []
        started = asyncio.Event()

        async def spawn(*args, **kwargs):
            p = await asyncio.create_subprocess_exec(
                sys.executable, "-c", "import time;time.sleep(60)", **kwargs
            )
            processes.append(p)
            started.set()
            return p

        async def resolve(host):
            return ["93.184.216.34"]

        transport = CurlPlaybackTransport(
            TargetPolicy(["media.example"], resolve=resolve), spawn=spawn
        )

        async def request():
            async with transport.open("https://media.example/v", {}):
                pass

        task = asyncio.create_task(request())
        await started.wait()
        await asyncio.sleep(0.03)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 2)
        assert processes[0].returncode is not None

    asyncio.run(run())


@pytest.mark.parametrize("cancel_cleanup", [False, True])
def test_close_while_read_is_pending_and_force_kill_unresponsive_worker(cancel_cleanup):
    from nassav.playback.curl_transport import CurlPlaybackTransport
    import sys

    async def run():
        processes = []

        async def spawn(*args, **kwargs):
            code = 'import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);print(\'{"status":200,"headers":{}}\',flush=True);time.sleep(60)'
            p = await asyncio.create_subprocess_exec(
                sys.executable, "-c", code, **kwargs
            )
            processes.append(p)
            return p

        async def resolve(host):
            return ["93.184.216.34"]

        transport = CurlPlaybackTransport(
            TargetPolicy(["media.example"], resolve=resolve), spawn=spawn
        )
        async with transport.open("https://media.example/v", {}) as (response, final):
            pending = asyncio.create_task(anext(response.aiter_raw()))
            await asyncio.sleep(0.03)
            if cancel_cleanup:
                closing = asyncio.create_task(response.aclose())
                await asyncio.sleep(0.03)
                closing.cancel()
                await asyncio.sleep(0.03)
                closing.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await asyncio.wait_for(closing, 2)
            else:
                await asyncio.wait_for(response.aclose(), 2)
            with pytest.raises(asyncio.CancelledError):
                await pending
            assert processes[0].returncode is not None

    asyncio.run(run())


def test_production_gateway_uses_generic_browser_capability(settings):
    from nassav.composition import build_playback_gateway
    from nassav.playback.curl_transport import CurlPlaybackTransport

    gateway = build_playback_gateway()
    try:
        assert isinstance(gateway.transport, CurlPlaybackTransport)
        assert gateway.transport.proxy == (
            settings.PROXY_URL if settings.PROXY_ENABLED else None
        )
    finally:
        gateway.registry.client.close()


def test_preheader_stop_keeps_capacity_until_pending_producer_is_stopped():
    from contextlib import asynccontextmanager
    from test_playback_gateway import make_gateway, Response
    from nassav.playback.contracts import PlaybackDescriptor
    from uuid import uuid4

    async def run():
        gateway, _, capacity, _ = make_gateway(Response(b"G"))
        started = asyncio.Event()
        stopping = asyncio.Event()
        reaped = asyncio.Event()
        stop = False

        class Transport:
            @asynccontextmanager
            async def open(self, *args, **kwargs):
                started.set()
                try:
                    await asyncio.Event().wait()
                    yield
                finally:
                    stopping.set()
                    await reaped.wait()

        gateway.transport = Transport()

        async def check():
            if stop:
                raise PlaybackGatewayError("session_closed", 410)

        d = PlaybackDescriptor(
            "https://media.example/v",
            "https://source.example/detail",
            "UA",
            "missav",
            None,
            None,
        )

        async def request():
            async with gateway.open(
                uuid4(),
                1,
                d,
                {"url": d.manifest_url, "kind": "segment", "depth": 0},
                check=check,
                asset_url=lambda a, k: a,
                ttl=300,
            ):
                pass

        task = asyncio.create_task(request())
        await started.wait()
        stop = True
        await asyncio.wait_for(stopping.wait(), 2)
        try:
            assert capacity.active == 1
        finally:
            reaped.set()
        with pytest.raises(PlaybackGatewayError, match="session_closed"):
            await task
        assert capacity.active == 0

    asyncio.run(run())
