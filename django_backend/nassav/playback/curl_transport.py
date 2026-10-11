"""Browser-capable PlaybackTransport with killable bounded producer processes."""

import asyncio
import json
import sys
from pathlib import Path
from contextlib import asynccontextmanager
from urllib.parse import urljoin
from nassav.constants import IMPERSONATE
from .policy import PlaybackGatewayError
from .transport import PlaybackTransport


async def finish_owned_task(task):
    """Repeated caller cancellation cannot abandon an owned process cleanup."""
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            continue
    return task.result()


class CurlStreamResponse:
    def __init__(self, process, status, headers):
        self.process, self.status_code, self.headers = process, status, headers
        self.closed = False
        self.close_task = None
        self.read_task = None

    async def aiter_raw(self, chunk_size=16384):
        if not 1 <= chunk_size <= 16384:
            raise ValueError("Invalid media chunk size")
        if self.process.stdout is None:
            raise PlaybackGatewayError("upstream_unavailable")
        while not self.closed:
            try:
                self.read_task = asyncio.create_task(
                    self.process.stdout.read(chunk_size)
                )
                data = await asyncio.wait_for(self.read_task, 15)
            except TimeoutError:
                raise PlaybackGatewayError("upstream_unavailable") from None
            if not data:
                if await self.process.wait() != 0:
                    raise PlaybackGatewayError("upstream_unavailable")
                return
            yield data

    async def aclose(self):
        if self.close_task is None:
            self.close_task = asyncio.create_task(self._close())
        try:
            await asyncio.shield(self.close_task)
        except asyncio.CancelledError:
            await finish_owned_task(self.close_task)
            raise

    async def _close(self):
        self.closed = True
        if self.read_task is not None and not self.read_task.done():
            self.read_task.cancel()
            await asyncio.gather(self.read_task, return_exceptions=True)
        process = self.process
        if process.returncode is None:
            try:
                process.terminate()
            except ProcessLookupError:
                pass

        async def drain():
            # wait() alone can deadlock on a paused stdout pipe.
            if process.stdout is not None:
                while await process.stdout.read(16384):
                    pass
            await process.wait()

        try:
            await asyncio.wait_for(drain(), 1)
        except TimeoutError:
            if process.returncode is None:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
            await drain()


class CurlPlaybackTransport(PlaybackTransport):
    def __init__(
        self,
        policy,
        proxy=None,
        *,
        proxy_targets_trusted=False,
        unix_socket_path=None,
        cacert=None,
        spawn=asyncio.create_subprocess_exec,
    ):
        self.policy, self.proxy, self.trusted = policy, proxy, proxy_targets_trusted
        self.unix_socket_path, self.cacert, self.spawn = unix_socket_path, cacert, spawn

    @asynccontextmanager
    async def single(self, url, headers, method):
        host, ip = await self.policy.target(url)
        options = {
            "url": url,
            "host": host,
            "ip": ip,
            "proxy": self.proxy,
            "method": method,
            "headers": {**headers, "Host": host, "Accept-Encoding": "identity"},
            "impersonate": IMPERSONATE,
            "unix_socket_path": self.unix_socket_path,
            "cacert": self.cacert,
        }
        if any(
            k.lower() in {"cookie", "authorization", "proxy-authorization"}
            or "\r" in k
            or "\n" in k
            or "\r" in v
            or "\n" in v
            for k, v in options["headers"].items()
        ):
            raise PlaybackGatewayError("invalid_media_headers")
        payload = json.dumps(options).encode()
        if len(payload) > 32768:
            raise PlaybackGatewayError("invalid_media_headers")
        creation = asyncio.create_task(
            self.spawn(
                sys.executable,
                str(Path(__file__).with_name("curl_worker.py")),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                limit=16384,
            )
        )
        response = None
        process = None
        try:
            try:
                process = await asyncio.shield(creation)
            except asyncio.CancelledError:
                process = await finish_owned_task(creation)
                raise
            response = CurlStreamResponse(process, 0, {})
            if process.stdin is None or process.stdout is None:
                raise PlaybackGatewayError("upstream_unavailable")
            process.stdin.write(payload)
            await process.stdin.drain()
            process.stdin.close()
            try:
                line = await asyncio.wait_for(process.stdout.readline(), 15)
                info = json.loads(line)
                status = info["status"]
                if type(status) is not int or not 200 <= status <= 599:
                    raise ValueError("Invalid upstream status")
                response.status_code, response.headers = status, info["headers"]
            except (ValueError, KeyError, TimeoutError):
                raise PlaybackGatewayError("upstream_unavailable") from None
            yield response
        finally:
            if response is None and process is not None:
                response = CurlStreamResponse(process, 0, {})
            if response is not None:
                cleanup = asyncio.create_task(response.aclose())
                try:
                    await asyncio.shield(cleanup)
                except asyncio.CancelledError:
                    await finish_owned_task(cleanup)
                    raise

    @asynccontextmanager
    async def open(self, url, headers, *, method="GET"):
        if method not in {"GET", "HEAD"}:
            raise PlaybackGatewayError("invalid_media_method")
        if self.proxy and not self.trusted:
            raise PlaybackGatewayError("proxy_target_policy_required", 503)
        for hop in range(4):
            async with self.single(url, headers, method) as response:
                if response.status_code not in {301, 302, 303, 307, 308}:
                    yield response, url
                    return
                destination = response.headers.get("location")
                if not destination or hop == 3:
                    raise PlaybackGatewayError("redirect_rejected")
                url = urljoin(url, destination)
