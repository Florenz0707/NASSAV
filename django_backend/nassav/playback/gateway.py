"""HLS orchestration: explicit registry/transport/capacity and live ownership checks."""

import asyncio
import re
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from collections.abc import AsyncIterator
from .manifest import parse_manifest
from .policy import PlaybackGatewayError


@dataclass
class GatewayResponse:
    status: int
    headers: dict
    body: AsyncIterator[bytes]


def range_header(value):
    if value is None:
        return None
    if len(value) > 80:
        raise PlaybackGatewayError("invalid_range", 416)
    match = re.fullmatch(r"bytes=(\d*)-(\d*)", value)
    if not match or not any(match.groups()):
        raise PlaybackGatewayError("invalid_range", 416)
    start, end = match.groups()
    if (start and end and int(start) > int(end)) or len(value) > 80:
        raise PlaybackGatewayError("invalid_range", 416)
    return value


async def read_limited(response, limit):
    body = bytearray()
    async for chunk in response.aiter_raw(chunk_size=16384):
        body.extend(chunk)
        if len(body) > limit:
            raise PlaybackGatewayError("upstream_body_too_large")
    return bytes(body)


class PlaybackGateway:
    def __init__(self, transport, policy, registry, capacity):
        self.transport, self.policy, self.registry, self.capacity = (
            transport,
            policy,
            registry,
            capacity,
        )

    @asynccontextmanager
    async def open(
        self,
        session_id,
        generation,
        descriptor,
        asset,
        *,
        check,
        asset_url,
        ttl,
        method="GET",
        range_value=None,
    ) -> AsyncIterator[GatewayResponse]:
        range_value = range_header(range_value)
        if range_value and asset["kind"] in {"key", "manifest", "data"}:
            raise PlaybackGatewayError("range_not_supported", 416)
        async with self.capacity.slot(session_id) as capacity_check:
            opened = False
            response = None
            started = time.monotonic()

            async def watch():
                try:
                    while True:
                        await check()
                        capacity_check()
                        if time.monotonic() - started >= 45:
                            raise PlaybackGatewayError("media_deadline_exceeded")
                        await asyncio.sleep(0.5)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    try:
                        if response is not None:
                            await response.aclose()
                    finally:
                        await capacity_check.release()
                    raise

            watcher = asyncio.create_task(watch())

            async def guarded(operation):
                task = asyncio.create_task(operation)
                try:
                    done, _ = await asyncio.wait(
                        [task, watcher], return_when=asyncio.FIRST_COMPLETED
                    )
                    if task in done:
                        return await task
                    if watcher in done:
                        await watcher
                        raise PlaybackGatewayError("session_closed", 410)
                    return await task
                finally:
                    if not task.done():
                        task.cancel()
                    await asyncio.gather(task, return_exceptions=True)

            headers = {
                "Referer": descriptor.referer,
                "User-Agent": descriptor.user_agent,
            }
            if range_value:
                if asset["kind"] in {"key", "manifest", "data"}:
                    raise PlaybackGatewayError("range_not_supported", 416)
                headers["Range"] = range_header(range_value)
            manager = self.transport.open(asset["url"], headers, method=method)
            opened = False
            try:
                await check()
                capacity_check()
                response, final = await guarded(manager.__aenter__())
                opened = True
                status = response.status_code
                result_headers = {
                    "Cache-Control": "no-store",
                    "X-Accel-Buffering": "no",
                    "X-Content-Type-Options": "nosniff",
                }
                if status == 416:
                    value = response.headers.get("content-range", "")
                    if re.fullmatch(r"bytes \*/\d+", value):
                        result_headers["Content-Range"] = value

                    async def empty():
                        if False:
                            yield b""

                    yield GatewayResponse(416, result_headers, empty())
                    return
                if status not in {200, 206}:
                    raise PlaybackGatewayError("upstream_status_rejected")
                encoding = response.headers.get("content-encoding", "identity")
                if encoding not in {"identity", ""}:
                    raise PlaybackGatewayError("encoded_media_rejected")
                length = response.headers.get("content-length")
                if length is not None and (
                    not length.isdigit() or int(length) > 16 * 1024 * 1024
                ):
                    raise PlaybackGatewayError("upstream_body_too_large")
                if status == 206:
                    content_range = response.headers.get("content-range", "")
                    match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", content_range)
                    if not range_value or not match:
                        raise PlaybackGatewayError("invalid_upstream_range")
                    first, last, total = map(int, match.groups())
                    request_range = re.fullmatch(r"bytes=(\d*)-(\d*)", range_value)
                    if request_range is None:
                        raise PlaybackGatewayError("invalid_upstream_range")
                    start, end = request_range.groups()
                    expected_first = int(start) if start else max(0, total - int(end))
                    expected_last = (
                        min(total - 1, int(end)) if start and end else total - 1
                    )
                    if (
                        first != expected_first
                        or last != expected_last
                        or first > last
                        or last >= total
                        or (length and int(length) != last - first + 1)
                    ):
                        raise PlaybackGatewayError("invalid_upstream_range")
                    result_headers["Content-Range"] = content_range
                if asset["kind"] == "manifest":
                    if method == "HEAD":
                        # A rewritten manifest has different length/validators.
                        async def empty():
                            if False:
                                yield b""

                        result_headers["Content-Type"] = "application/vnd.apple.mpegurl"
                        yield GatewayResponse(200, result_headers, empty())
                        return
                    body = await guarded(read_limited(response, 1024 * 1024))
                    parsed = parse_manifest(body, final, self.policy)
                    hosts = {
                        self.policy.validate(ref.url): ref.url
                        for ref in parsed.references
                    }
                    for url in hosts.values():
                        await guarded(self.policy.target(url))
                    replacements = []
                    for ref in parsed.references:
                        aid = await guarded(
                            asyncio.to_thread(
                                self.registry.register,
                                session_id,
                                generation,
                                ref.url,
                                ref.kind,
                                asset["depth"] + 1,
                                ttl,
                            )
                        )
                        replacements.append(asset_url(aid, ref.kind))
                    body = parsed.render(replacements)
                    result_headers.update(
                        {
                            "Content-Type": "application/vnd.apple.mpegurl",
                            "Content-Length": str(len(body)),
                        }
                    )

                    async def manifest_body():
                        await check()
                        capacity_check()
                        yield body

                    yield GatewayResponse(200, result_headers, manifest_body())
                    return
                result_headers["Content-Type"] = "application/octet-stream"
                result_headers["Accept-Ranges"] = "bytes"
                if length:
                    result_headers["Content-Length"] = length
                if method == "HEAD":

                    async def empty():
                        if False:
                            yield b""

                    yield GatewayResponse(status, result_headers, empty())
                    return
                if asset["kind"] in {"key", "data"}:
                    body = await guarded(
                        read_limited(response, 16 if asset["kind"] == "key" else 65536)
                    )
                    if asset["kind"] == "key" and len(body) != 16:
                        raise PlaybackGatewayError("invalid_aes_key")
                    result_headers["Content-Length"] = str(len(body))

                    async def fixed():
                        await check()
                        capacity_check()
                        yield body

                    yield GatewayResponse(status, result_headers, fixed())
                    return
                chunks = response.aiter_raw(chunk_size=16384)
                try:
                    first_chunk = await guarded(anext(chunks))
                except StopAsyncIteration:
                    raise PlaybackGatewayError("empty_media")
                probe = first_chunk.lstrip().lower()
                if (
                    probe.startswith((b"<!doctype", b"<html", b"<head", b"<body"))
                    or "text/html" in response.headers.get("content-type", "").lower()
                ):
                    raise PlaybackGatewayError("html_media_rejected")

                async def media_body():
                    count = 0
                    chunk = first_chunk
                    while True:
                        await check()
                        capacity_check()
                        count += len(chunk)
                        if count > 16 * 1024 * 1024:
                            raise PlaybackGatewayError("upstream_body_too_large")
                        yield chunk
                        try:
                            chunk = await guarded(anext(chunks))
                        except StopAsyncIteration:
                            break
                    if length and count != int(length):
                        raise PlaybackGatewayError("truncated_media")

                yield GatewayResponse(status, result_headers, media_body())
            finally:
                try:
                    if opened:
                        await manager.__aexit__(None, None, None)
                finally:
                    watcher.cancel()
                    await asyncio.gather(watcher, return_exceptions=True)
