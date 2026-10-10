"""Authenticated preparation snapshots; no upstream URL is returned."""

from uuid import UUID
from django.conf import settings
from rest_framework.response import Response
from nassav.http_base import SchemaAPIView
from nassav.playback import records


class PlaybackSessionView(SchemaAPIView):
    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "no-store"
        return response

    def get(self, request, session_id):
        if not settings.PLAYBACK_ENABLED:
            return Response(
                {"code": 404, "message": "在线播放未启用", "data": None}, status=404
            )
        try:
            row = records.owned(
                session_id, request.user.pk, request.session.session_key
            )
            from nassav.playback.models import PlaybackSession
            from django.utils import timezone

            now = timezone.now()
            if row.state not in {"failed", "closed"} and (
                min(row.idle_expires_at, row.absolute_expires_at) <= now
                or (
                    row.state in {"queued", "resolving"} and row.prepare_deadline <= now
                )
                or (
                    row.state == "resolving"
                    and row.lease_until
                    and row.lease_until <= now
                )
            ):
                PlaybackSession.objects.filter(pk=row.pk, version=row.version).update(
                    state="failed",
                    error_code="expired",
                    descriptor={},
                    version=row.version + 1,
                    updated_at=now,
                )
                row = records.owned(
                    session_id, request.user.pk, request.session.session_key
                )
            data = records.snapshot(row)
            if row.state == "ready":
                from nassav.http.playback_media import root_url
                from nassav.playback.policy import PlaybackGatewayError

                try:
                    data["manifest_url"] = root_url(row)
                except PlaybackGatewayError as error:
                    return Response(
                        {"code": error.status, "message": error.code, "data": None},
                        status=error.status,
                    )
                except Exception:
                    return Response(
                        {"code": 503, "message": "playback_unavailable", "data": None},
                        status=503,
                    )
            return Response({"code": 200, "message": "success", "data": data})
        except records.PlaybackSession.DoesNotExist:
            return Response(
                {"code": 404, "message": "播放会话不存在", "data": None}, status=404
            )

    def post(self, request, avid=None, session_id=None):
        if not settings.PLAYBACK_ENABLED:
            return Response(
                {"code": 404, "message": "在线播放未启用", "data": None}, status=404
            )
        try:
            command_id = UUID(str(request.data.get("request_id")))
            if avid:
                row = records.submit(
                    request.user.pk,
                    request.session.session_key,
                    avid.upper(),
                    command_id,
                )
                # Recovery retries broker failures; no network inside creation transaction.
                from nassav.tasks import playback_prepare_task

                try:
                    playback_prepare_task.apply_async(
                        args=(str(row.pk),), queue="scrape"
                    )
                except Exception:
                    pass
                status = 202
            else:
                version = request.data.get("expected_version")
                if type(version) is not int or version < 1:
                    raise ValueError("Invalid version")
                row = records.close(
                    session_id,
                    request.user.pk,
                    request.session.session_key,
                    version,
                    command_id,
                )
                status = 200
            return Response(
                {"code": status, "message": "success", "data": records.snapshot(row)},
                status=status,
            )
        except (records.PlaybackSession.DoesNotExist, records.AVResource.DoesNotExist):
            return Response(
                {"code": 404, "message": "资源或会话不存在", "data": None}, status=404
            )
        except records.PlaybackStopped:
            return Response(
                {"code": 409, "message": "会话状态冲突或达到容量限制", "data": None},
                status=409,
            )
        except (TypeError, ValueError, AttributeError):
            return Response(
                {"code": 400, "message": "请求参数无效", "data": None}, status=400
            )


class PlaybackSubmitView(PlaybackSessionView):
    http_method_names = ["post", "options"]


class PlaybackStatusView(PlaybackSessionView):
    http_method_names = ["get", "options"]


class PlaybackCloseView(PlaybackSessionView):
    http_method_names = ["post", "options"]
