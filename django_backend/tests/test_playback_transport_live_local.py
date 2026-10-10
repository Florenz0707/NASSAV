"""Real TLS/HTTPX stream over a private Unix socket; no external network."""

import asyncio
import ssl
import tracemalloc
from datetime import datetime, timedelta, timezone
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
import httpx
from nassav.playback.transport import HttpxPlaybackTransport
from nassav.playback.policy import TargetPolicy


def test_real_tls_stream_has_bounded_memory_and_early_close(tmp_path):
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
    cert_path = tmp_path / "cert.pem"
    key_path = tmp_path / "key.pem"
    socket = tmp_path / "tls.sock"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    server_ssl = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_ssl.load_cert_chain(cert_path, key_path)

    async def run():
        finished = asyncio.Event()
        received = {}
        handlers = set()

        async def handler(reader, writer):
            task = asyncio.current_task()
            handlers.add(task)
            try:
                request = await reader.readuntil(b"\r\n\r\n")
                received["request"] = request
                writer.write(
                    b"HTTP/1.1 200 OK\r\nContent-Length: 16777216\r\nContent-Type: video/mp2t\r\nConnection: close\r\n\r\n"
                )
                for _ in range(256):
                    writer.write(b"G" + b"x" * 65535)
                    await writer.drain()
                    await asyncio.sleep(0.001)
            except (ConnectionError, ssl.SSLError):
                pass
            finally:
                writer.close()
                try:
                    await writer.wait_closed()
                except (ConnectionError, ssl.SSLError):
                    pass
                handlers.discard(task)
                finished.set()

        server = await asyncio.start_unix_server(handler, str(socket), ssl=server_ssl)

        async def resolve(host):
            return ["93.184.216.34"]

        policy = TargetPolicy(["media.example"], resolve=resolve)

        def factory(**kwargs):
            context = ssl.create_default_context(cafile=str(cert_path))
            return httpx.AsyncClient(
                transport=httpx.AsyncHTTPTransport(uds=str(socket), verify=context),
                trust_env=False,
            )

        transport = HttpxPlaybackTransport(policy, client_factory=factory)
        try:
            tracemalloc.start()
            async with transport.open(
                "https://media.example/video.ts",
                {
                    "Referer": "https://source.example/detail",
                    "User-Agent": "fixture-UA",
                },
            ) as (response, final):
                iterator = response.aiter_raw(chunk_size=16384)
                assert len(await anext(iterator)) == 16384
                await asyncio.sleep(0.1)
                peak = tracemalloc.get_traced_memory()[1]
                assert peak < 3 * 1024 * 1024
                assert final == "https://media.example/video.ts"
            await asyncio.wait_for(finished.wait(), 2)
            assert b"Host: media.example" in received["request"]
            assert b"Cookie:" not in received["request"]
        finally:
            tracemalloc.stop()
            server.close()
            await server.wait_closed()
            for task in list(handlers):
                task.cancel()
            if handlers:
                await asyncio.gather(*handlers, return_exceptions=True)

    asyncio.run(run())
