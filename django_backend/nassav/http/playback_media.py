"""Native Django async media entry: session cookie + signed opaque assets."""

import asyncio
from asgiref.sync import sync_to_async
from django.conf import settings
from django.core import signing
from django.http import HttpResponse, JsonResponse, StreamingHttpResponse
from django.utils import timezone
from django.contrib.sessions.models import Session
from nassav.access import is_operator
from nassav.playback import records
from nassav.playback.contracts import PlaybackDescriptor
from nassav.playback.policy import PlaybackGatewayError
from nassav.source.CookieRepository import proxy_route_profile


class PlaybackStreamingResponse(StreamingHttpResponse):
    def __init__(self, *args, on_close, **kwargs):
        self.on_close = on_close
        super().__init__(*args, **kwargs)

    def close(self):
        self.on_close()
        super().close()


def capability(session_id, generation, asset_id):
    return signing.TimestampSigner(salt="nassav-playback-media").sign(
        f"{session_id}:{generation}:{asset_id}"
    )


def asset_url(session_id, generation, asset_id, kind):
    from urllib.parse import quote

    path = "manifest" if kind == "manifest" else "assets"
    return f"/nassav/api/playback-sessions/{session_id}/{path}/{asset_id}?cap=" + quote(
        capability(session_id, generation, asset_id), safe=""
    )


def authorize(request, session_id, generation=None):
    if not settings.PLAYBACK_ENABLED:
        raise PlaybackGatewayError("playback_disabled", 404)
    if not is_operator(request.user):
        raise PlaybackGatewayError("authentication_required", 401)
    key = request.session.session_key
    if (
        not key
        or not Session.objects.filter(
            session_key=key, expire_date__gt=timezone.now()
        ).exists()
    ):
        raise PlaybackGatewayError("login_expired", 401)
    try:
        row = records.owned(session_id, request.user.pk, key)
    except records.PlaybackSession.DoesNotExist:
        raise PlaybackGatewayError("session_not_found", 404)
    now = timezone.now()
    if (
        row.state != "ready"
        or min(row.idle_expires_at, row.absolute_expires_at) <= now
        or (generation is not None and row.generation != generation)
    ):
        raise PlaybackGatewayError("session_closed", 410)
    from datetime import timedelta

    if not records.PlaybackSession.objects.filter(
        pk=row.pk,
        state="ready",
        generation=row.generation,
        idle_expires_at__gt=now,
        absolute_expires_at__gt=now,
    ).update(
        last_seen_at=now,
        idle_expires_at=min(
            now + timedelta(seconds=records.IDLE_SECONDS), row.absolute_expires_at
        ),
    ):
        raise PlaybackGatewayError("session_closed", 410)
    descriptor = PlaybackDescriptor(**row.descriptor).validate()
    proxy = settings.PROXY_URL if settings.PROXY_ENABLED else None
    if descriptor.route_profile != proxy_route_profile(proxy):
        raise PlaybackGatewayError("playback_route_changed", 409)
    return row, descriptor


def root_url(row):
    from nassav.composition import build_playback_registry
    from nassav.playback.policy import TargetPolicy

    descriptor = PlaybackDescriptor(**row.descriptor).validate()
    TargetPolicy(settings.PLAYBACK_ALLOWED_HOSTS).validate(descriptor.manifest_url)
    registry = build_playback_registry()
    try:
        aid = registry.register(
            row.pk,
            row.generation,
            descriptor.manifest_url,
            "manifest",
            0,
            (row.absolute_expires_at - timezone.now()).total_seconds(),
        )
        return asset_url(row.pk, row.generation, aid, "manifest")
    finally:
        registry.client.close()


async def media_view(request, session_id, asset_id):
    if request.method not in {"GET", "HEAD"}:
        return HttpResponse(status=405)
    manager = None
    opened = False
    gateway = None
    transferred = False
    try:
        row, descriptor = await sync_to_async(authorize)(request, session_id)
        try:
            token = signing.TimestampSigner(salt="nassav-playback-media").unsign(
                request.GET.get("cap", ""), max_age=records.MAX_SECONDS
            )
            if token != f"{session_id}:{row.generation}:{asset_id}":
                raise signing.BadSignature
        except signing.BadSignature:
            raise PlaybackGatewayError("invalid_capability", 403)
        from nassav.composition import build_playback_gateway

        gateway = build_playback_gateway()
        try:
            asset = await asyncio.to_thread(
                gateway.registry.get, row.pk, row.generation, asset_id
            )
        except Exception:
            gateway.registry.client.close()
            raise
        if ("/manifest/" in request.path) != (asset["kind"] == "manifest"):
            gateway.registry.client.close()
            raise PlaybackGatewayError("asset_kind_mismatch", 404)

        async def check():
            await sync_to_async(authorize)(request, session_id, row.generation)

        manager = gateway.open(
            row.pk,
            row.generation,
            descriptor,
            asset,
            check=check,
            asset_url=lambda aid, kind: asset_url(row.pk, row.generation, aid, kind),
            ttl=(row.absolute_expires_at - timezone.now()).total_seconds(),
            method=request.method,
            range_value=request.headers.get("Range"),
        )
        result = await manager.__aenter__()
        opened = True
        closed = False
        close_lock = asyncio.Lock()

        async def cleanup():
            nonlocal closed
            async with close_lock:
                if not closed:
                    closed = True
                    try:
                        await manager.__aexit__(None, None, None)
                    finally:
                        gateway.registry.client.close()

        if request.method == "HEAD" or result.status == 416:
            await cleanup()
            opened = False
            return HttpResponse(status=result.status, headers=result.headers)

        async def body():
            try:
                async for chunk in result.body:
                    yield chunk
            finally:
                await cleanup()

        loop = asyncio.get_running_loop()

        def schedule_cleanup():
            if not loop.is_closed():
                loop.call_soon_threadsafe(lambda: asyncio.create_task(cleanup()))

        response = PlaybackStreamingResponse(
            body(),
            status=result.status,
            headers=result.headers,
            on_close=schedule_cleanup,
        )
        transferred = True
        return response
    except asyncio.CancelledError:
        raise
    except PlaybackGatewayError as error:
        return JsonResponse(
            {"code": error.status, "message": error.code, "data": None},
            status=error.status,
            headers={"Cache-Control": "no-store"},
        )
    except Exception:
        return JsonResponse(
            {"code": 503, "message": "playback_unavailable", "data": None},
            status=503,
            headers={"Cache-Control": "no-store"},
        )

    finally:
        if not transferred:
            try:
                if opened and manager is not None:
                    await manager.__aexit__(None, None, None)
            finally:
                if gateway is not None:
                    gateway.registry.client.close()
