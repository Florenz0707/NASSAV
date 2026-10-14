"""Authenticated personal history and watch-later projections."""

from django.conf import settings
from rest_framework.response import Response
from nassav.http_base import SchemaAPIView
from nassav.playback import records
from nassav.playback.policy import PlaybackGatewayError
from nassav.viewing import (
    list_viewing,
    record_view,
    remove_history,
    remove_watched_later,
)


class PersonalViewingView(SchemaAPIView):
    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        return response

    def get(self, request, kind):
        try:
            page = int(request.query_params.get("page", "1"))
            size = int(request.query_params.get("page_size", "15"))
            if page < 1 or not 1 <= size <= 200:
                raise ValueError("Invalid page")
            data, pagination = list_viewing(request.user.pk, kind, page, size)
            return Response(
                {
                    "code": 200,
                    "message": "success",
                    "data": data,
                    "pagination": pagination,
                }
            )
        except (ValueError, TypeError):
            return Response(
                {"code": 400, "message": "列表参数无效", "data": None}, status=400
            )

    def delete(self, request, kind):
        try:
            if kind != "history" or set(request.data) != {"entries"}:
                raise ValueError("历史记录参数无效")
            data = remove_history(request.user.pk, request.data["entries"])
            return Response({"code": 200, "message": "success", "data": data})
        except (ValueError, TypeError, AttributeError) as error:
            return Response(
                {"code": 400, "message": str(error), "data": None}, status=400
            )

    def post(self, request, kind):
        try:
            if kind != "watch-later" or request.data != {"action": "remove_watched"}:
                raise ValueError("稍后再看操作无效")
            count = remove_watched_later(request.user.pk)
            return Response(
                {"code": 200, "message": "success", "data": {"removed": count}}
            )
        except (ValueError, TypeError, AttributeError) as error:
            return Response(
                {"code": 400, "message": str(error), "data": None}, status=400
            )


class PersonalHistoryView(PersonalViewingView):
    http_method_names = ["get", "delete", "options"]


class PersonalWatchLaterView(PersonalViewingView):
    http_method_names = ["get", "post", "options"]


class PlaybackViewedView(PersonalViewingView):
    http_method_names = ["post", "options"]

    def post(self, request, session_id):
        try:
            if not settings.PLAYBACK_ENABLED:
                raise PlaybackGatewayError("playback_disabled", 404)
            data = record_view(
                session_id,
                request.user.pk,
                request.session.session_key,
                request.data.get("session_generation"),
                request.data.get("sequence"),
            )
            return Response({"code": 200, "message": "success", "data": data})
        except records.PlaybackSession.DoesNotExist:
            return Response(
                {"code": 404, "message": "播放会话不存在", "data": None}, status=404
            )
        except PlaybackGatewayError as error:
            return Response(
                {"code": error.status, "message": error.code, "data": None},
                status=error.status,
            )
        except (ValueError, TypeError, AttributeError):
            return Response(
                {"code": 400, "message": "播放参数无效", "data": None}, status=400
            )
