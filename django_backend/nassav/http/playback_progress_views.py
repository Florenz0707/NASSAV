"""Owned progress APIs; media identity always comes from the server session."""

from uuid import UUID
from django.conf import settings
from rest_framework.response import Response
from nassav.http_base import SchemaAPIView
from nassav.playback import progress, records
from nassav.playback.policy import PlaybackGatewayError


class PlaybackProgressView(SchemaAPIView):
    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "no-store"
        return response

    def handle(self, request, session_id=None, avid=None):
        try:
            if not settings.PLAYBACK_ENABLED:
                raise PlaybackGatewayError("playback_disabled", 404)
            if request.method == "DELETE":
                from nassav.task_control_rules import normalize_avid

                if not isinstance(avid, str):
                    raise ValueError("Invalid resource")
                progress.clear(request.user.pk, normalize_avid(avid))
                data = None
            else:
                row = records.owned(
                    session_id, request.user.pk, request.session.session_key
                )
                progress.active(row)
                if row.media_kind == "local":
                    from nassav.http.playback_local_media import check_local

                    check_local(row)
                if request.method == "GET":
                    data = progress.query(row)
                elif request.method == "POST":
                    generation = request.data.get("session_generation")
                    if type(generation) is not int or generation < 1:
                        raise ValueError("Invalid generation")
                    expected = request.data.get("expected_writer_generation")
                    if type(expected) is not int or expected < 0:
                        raise ValueError("Invalid writer generation")
                    data = progress.claim(
                        session_id,
                        request.user.pk,
                        request.session.session_key,
                        generation,
                        UUID(str(request.data.get("request_id"))),
                        expected,
                    )
                else:
                    data = progress.save(
                        session_id,
                        request.user.pk,
                        request.session.session_key,
                        request.data,
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
                {"code": 400, "message": "进度参数无效", "data": None}, status=400
            )

    get = handle
    put = handle


class PlaybackProgressClaimView(PlaybackProgressView):
    http_method_names = ["post", "options"]
    post = PlaybackProgressView.handle


class PlaybackProgressClearView(PlaybackProgressView):
    http_method_names = ["delete", "options"]
    delete = PlaybackProgressView.handle
