"""Bounded reads for metadata and tiny assets, never full video segments."""

from .policy import PlaybackGatewayError


async def read_limited(response, limit):
    body = bytearray()
    async for chunk in response.aiter_raw(chunk_size=16384):
        body.extend(chunk)
        if len(body) > limit:
            raise PlaybackGatewayError("upstream_body_too_large")
    return bytes(body)
