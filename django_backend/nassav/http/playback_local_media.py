"""Same-origin, login-bound published video delivery; no source preparation."""

import asyncio
from urllib.parse import quote
from asgiref.sync import sync_to_async
from django.core import signing
from django.http import HttpResponse, JsonResponse
from nassav.playback import records
from nassav.playback.async_cleanup import finish_owned_task
from nassav.playback.policy import PlaybackGatewayError
from .playback_media import authorize_session, capability, PlaybackStreamingResponse


def local_url(row):
    return f"/nassav/api/playback-sessions/{row.pk}/file?cap=" + quote(
        capability(row.pk, row.generation, "file"), safe=""
    )


def check_local(row, locator=None):
    if row.media_kind != "local":
        raise PlaybackGatewayError("media_kind_mismatch", 404)
    if locator is None:
        from nassav.composition import build_local_video_locator

        from django.conf import settings

        locator = (
            build_local_video_locator(session=row)
            if settings.SHARED_LIBRARY_ENABLED
            else build_local_video_locator()
        )
    try:
        locator.check(row.resource.avid, row.descriptor)
    except PlaybackGatewayError as error:
        from django.db.models import F
        from django.utils import timezone

        records.PlaybackSession.objects.filter(
            pk=row.pk, generation=row.generation, state="ready"
        ).update(
            state="failed",
            error_code=error.code,
            descriptor={},
            version=F("version") + 1,
            updated_at=timezone.now(),
        )
        raise


async def local_media_view(request, session_id):
    if request.method not in {"GET", "HEAD"}:
        return HttpResponse(
            status=405, headers={"Allow": "GET, HEAD", "Cache-Control": "no-store"}
        )
    gateway = None
    manager = None
    opened = False
    transferred = False
    cleanup_task = None
    version_read = None

    async def cleanup():
        nonlocal cleanup_task

        async def operation():
            try:
                if opened and manager is not None:
                    await manager.__aexit__(None, None, None)
            finally:
                try:
                    if version_read is not None:
                        await sync_to_async(version_read.close)()
                finally:
                    if gateway is not None:
                        gateway.capacity.client.close()

        if cleanup_task is None:
            cleanup_task = asyncio.create_task(operation())
        try:
            await asyncio.shield(cleanup_task)
        except asyncio.CancelledError:
            await finish_owned_task(cleanup_task)
            raise

    try:
        row = await sync_to_async(authorize_session)(request, session_id)
        if row.library_grant.get("version_id"):
            from nassav.composition import build_playback_version_read

            version_read = build_playback_version_read(row, request.session.session_key)
        try:
            token = signing.TimestampSigner(salt="nassav-playback-media").unsign(
                request.GET.get("cap", ""), max_age=records.MAX_SECONDS
            )
            if token != f"{session_id}:{row.generation}:file":
                raise signing.BadSignature
        except signing.BadSignature:
            raise PlaybackGatewayError("invalid_capability", 403)
        from nassav.composition import (
            build_local_video_locator,
            build_local_playback_gateway,
        )

        from django.conf import settings

        locator = (
            await sync_to_async(build_local_video_locator)(session=row)
            if settings.SHARED_LIBRARY_ENABLED
            else await sync_to_async(build_local_video_locator)()
        )
        avid = await sync_to_async(lambda: row.resource.avid)()
        await sync_to_async(check_local)(row, locator)
        gateway = build_local_playback_gateway()

        async def check():
            current = await sync_to_async(authorize_session)(
                request, session_id, row.generation
            )
            await sync_to_async(check_local)(current, locator)
            if version_read is not None:
                await sync_to_async(version_read.check)()

        async def opener():
            return await sync_to_async(locator.open)(avid, row.descriptor)

        serving_task = asyncio.current_task()

        def stop_transfer():
            if serving_task is not None:
                serving_task.cancel()

        manager = gateway.open(
            row.pk,
            row.descriptor,
            opener=opener,
            check=check,
            method=request.method,
            range_value=request.headers.get("Range"),
            if_range=request.headers.get("If-Range"),
            stopped=stop_transfer,
        )
        result = await manager.__aenter__()
        opened = True
        if request.method == "HEAD" or result.status == 416:
            await cleanup()
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
            await cleanup()
