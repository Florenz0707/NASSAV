"""Bounded local file delivery with independent revocation and capacity cleanup."""

import asyncio
import hashlib
import json
import time
from contextlib import asynccontextmanager
from .async_cleanup import finish_owned_task
from .gateway import GatewayResponse, range_header
from .policy import PlaybackGatewayError


def select_range(value, size):
    range_header(value)
    start, end = value[6:].split("-")
    first = int(start) if start else max(0, size - int(end))
    last = min(size - 1, int(end)) if start and end else size - 1
    if first >= size or last < first or (not start and int(end) == 0):
        raise PlaybackGatewayError("invalid_range", 416)
    return first, last


class LocalPlaybackGateway:
    def __init__(self, capacity, *, idle_seconds=30):
        self.capacity, self.idle_seconds = capacity, idle_seconds

    @asynccontextmanager
    async def open(
        self,
        session_id,
        descriptor,
        *,
        opener,
        check,
        method="GET",
        range_value=None,
        if_range=None,
        stopped=lambda: None,
    ):
        async with self.capacity.slot(session_id) as lease:
            video = None
            watcher = None
            close_task = None
            last_read = time.monotonic()

            async def close():
                nonlocal close_task

                async def operation():
                    try:
                        if video is not None:
                            await asyncio.to_thread(video.close)
                    finally:
                        await lease.release()

                if close_task is None:
                    close_task = asyncio.create_task(operation())
                try:
                    await asyncio.shield(close_task)
                except asyncio.CancelledError:
                    await finish_owned_task(close_task)
                    raise

            async def watch():
                try:
                    while True:
                        await check()
                        lease()
                        if time.monotonic() - last_read > self.idle_seconds:
                            raise PlaybackGatewayError("local_read_idle", 410)
                        await asyncio.sleep(0.5)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    await close()
                    stopped()
                    raise

            async def read(offset, size):
                # Cancellation cannot abandon a thread using an FD that may be reused.
                if video is None:
                    raise PlaybackGatewayError("local_media_unavailable", 410)
                task = asyncio.create_task(asyncio.to_thread(video.read, offset, size))
                try:
                    return await asyncio.shield(task)
                except asyncio.CancelledError:
                    await finish_owned_task(task)
                    raise

            try:
                await check()
                opening = asyncio.create_task(opener())
                try:
                    video = await asyncio.shield(opening)
                except asyncio.CancelledError:
                    video = await finish_owned_task(opening)
                    raise
                lease()
                await check()
                size = descriptor["fingerprint"][2]
                etag = (
                    '"'
                    + hashlib.sha256(
                        json.dumps(descriptor, sort_keys=True).encode()
                    ).hexdigest()
                    + '"'
                )
                headers = {
                    "Content-Type": "video/mp4",
                    "Accept-Ranges": "bytes",
                    "Cache-Control": "no-store",
                    "X-Accel-Buffering": "no",
                    "X-Content-Type-Options": "nosniff",
                    "ETag": etag,
                }
                first, last, status = 0, size - 1, 200
                # HEAD describes the full representation; weak/date If-Range fails
                # conservatively to 200. We expose only a strong ETag validator.
                if (
                    range_value
                    and method != "HEAD"
                    and (if_range is None or if_range == etag)
                ):
                    try:
                        first, last = select_range(range_value, size)
                        status = 206
                        headers["Content-Range"] = f"bytes {first}-{last}/{size}"
                    except PlaybackGatewayError:
                        status = 416
                        headers["Content-Range"] = f"bytes */{size}"
                headers["Content-Length"] = str(
                    last - first + 1 if status != 416 else 0
                )
                watcher = asyncio.create_task(watch())

                async def body():
                    nonlocal last_read
                    if method == "HEAD" or status == 416:
                        return
                    offset = first
                    while offset <= last:
                        if watcher.done():
                            await watcher
                        lease()
                        chunk = await read(offset, min(65536, last - offset + 1))
                        if not chunk:
                            raise PlaybackGatewayError("local_media_truncated", 410)
                        if watcher.done():
                            await watcher
                        last_read = time.monotonic()
                        offset += len(chunk)
                        yield chunk

                yield GatewayResponse(status, headers, body())
            finally:
                if watcher is not None:
                    watcher.cancel()
                    await asyncio.gather(watcher, return_exceptions=True)
                await close()
