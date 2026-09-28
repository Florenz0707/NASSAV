"""Reject cross-origin browser WebSocket handshakes before authentication."""

from urllib.parse import urlsplit


class SameOriginWebSocketValidator:
    def __init__(self, application):
        self.application = application

    async def __call__(self, scope, receive, send):
        headers = dict(scope.get("headers", []))
        try:
            origin = urlsplit(headers[b"origin"].decode("ascii"))
            host = headers[b"host"].decode("ascii").lower()
        except (KeyError, UnicodeDecodeError, ValueError):
            await send({"type": "websocket.close", "code": 4403})
            return
        forwarded = headers.get(b"x-forwarded-proto", b"").decode(
            "ascii", errors="ignore"
        )
        expected_scheme = (
            forwarded
            if forwarded in {"http", "https"}
            else ("https" if scope.get("scheme") == "wss" else "http")
        )
        if (
            origin.scheme != expected_scheme
            or origin.netloc.lower() != host
            or origin.path
            or origin.query
            or origin.fragment
            or origin.username
            or origin.password
        ):
            await send({"type": "websocket.close", "code": 4403})
            return
        await self.application(scope, receive, send)
