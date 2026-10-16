"""
API视图：实现资源管理接口
所有信息以 resource 目录中的实际资源为准
统一响应格式: {"code": xxx, "message": xxx, "data": data}
"""

from django.conf import settings
from django.http import FileResponse
from django.utils.http import http_date
from loguru import logger
from rest_framework import status
from rest_framework.response import Response

from nassav.api_utils import build_response
from nassav.http_base import SchemaAPIView
from nassav.utils import (
    parse_http_if_modified_since,
)


class ActorAvatarView(SchemaAPIView):
    """GET /api/actors/<int:actor_id>/avatar - 返回演员头像图片"""

    def get(self, request, actor_id):
        from nassav.library_catalog import enabled

        if enabled(request.user.pk):
            from nassav.http.version_media import catalog_avatar_response

            return catalog_avatar_response(request, actor_id)
        from pathlib import Path

        from django.conf import settings
        from django.http import FileResponse, HttpResponse

        from nassav.models import Actor

        try:
            actor = Actor.objects.get(id=actor_id)
        except Actor.DoesNotExist:
            return HttpResponse("演员不存在", status=404)

        if not actor.avatar_filename:
            return HttpResponse("演员头像不存在", status=404)

        avatar_path = Path(settings.AVATAR_DIR) / actor.avatar_filename
        if not avatar_path.exists():
            return HttpResponse("头像文件不存在", status=404)

        # 返回图片文件
        response = FileResponse(avatar_path.open("rb"), content_type="image/jpeg")
        response["Content-Disposition"] = f'inline; filename="{actor.avatar_filename}"'
        return response


class ResourceCoverView(SchemaAPIView):
    """
    GET /api/resource/cover?avid=
    根据avid获取封面图片
    """

    def get(self, request):
        from nassav.composition import build_cover_locator
        from nassav.resource_media import InvalidThumbnailSize

        avid = request.query_params.get("avid", "").upper()
        if not avid:
            return build_response(400, "avid参数缺失", None)
        from nassav.library_catalog import enabled, own_entry

        if enabled(request.user.pk):
            entry = own_entry(request.user.pk, avid=avid)
            if entry.current_version is not None:
                from nassav.resource_media import FileCoverLocator

                size = request.query_params.get("size")
                if size and str(size).lower() not in FileCoverLocator.SIZES:
                    return build_response(
                        400, "size 参数无效，支持 small|medium|large", None
                    )
                from nassav.http.version_media import image_response

                return image_response(request, entry)
        try:
            asset = build_cover_locator().locate(avid, request.query_params.get("size"))
        except InvalidThumbnailSize as error:
            return build_response(400, str(error), None)
        if asset is None:
            return Response(
                {"code": 404, "message": f"封面 {avid} 不存在", "data": None},
                status=status.HTTP_404_NOT_FOUND,
            )
        if enabled(request.user.pk) or settings.MULTI_USER_ENABLED:
            from nassav.http.image_cache import authorized_image, file_validator

            handle = asset.path.open("rb")
            try:
                validator = file_validator(handle)
            except BaseException:
                handle.close()
                raise
            return authorized_image(request, handle, asset.content_type, validator)
        modified = asset.path.stat().st_mtime
        if asset.etag is not None:
            inm = request.headers.get("If-None-Match") or request.META.get(
                "HTTP_IF_NONE_MATCH"
            )
            ims = request.headers.get("If-Modified-Since") or request.META.get(
                "HTTP_IF_MODIFIED_SINCE"
            )
            ims_ts = parse_http_if_modified_since(ims)
            if (inm and inm.strip() == asset.etag) or (
                ims_ts is not None and int(modified) <= ims_ts
            ):
                response = Response(status=status.HTTP_304_NOT_MODIFIED)
                response["ETag"] = asset.etag
                response["Last-Modified"] = http_date(modified)
                if enabled(request.user.pk):
                    response["Cache-Control"] = "private, no-store"
                    response["Vary"] = "Cookie"
                return response
        response = FileResponse(
            open(asset.path, "rb"), content_type=asset.content_type, as_attachment=False
        )
        response["Cache-Control"] = "public, max-age=31536000"
        if enabled(request.user.pk):
            response["Cache-Control"] = "private, no-store"
            response["Vary"] = "Cookie"
        response["Last-Modified"] = http_date(modified)
        if asset.etag is not None:
            response["ETag"] = asset.etag
        return response


class ResourcePreviewView(SchemaAPIView):
    """GET /api/resource/{avid}/preview - 返回 metadata + thumbnail_url（small 默认为首屏预览）"""

    def get(self, request, avid):
        avid = avid.upper()
        from nassav.library_catalog import enabled, own_entry, project

        if enabled(request.user.pk):
            data = project(own_entry(request.user.pk, avid=avid), detail=True)
            response = build_response(
                200,
                "success",
                {"metadata": data, "thumbnail_url": data["thumbnail_url"]},
            )
            response["Cache-Control"] = "private, no-store"
            response["Vary"] = "Cookie"
            return response
        # load metadata from DB if exists
        try:
            from nassav.models import AVResource

            resource = AVResource.objects.filter(avid=avid).first()
            if not resource:
                return build_response(404, f"资源 {avid} 不存在", None)

            metadata = (
                resource.metadata
                if resource.metadata
                else {
                    "avid": resource.avid,
                    "original_title": resource.original_title,
                    "source_title": resource.source_title,
                    "translated_title": resource.translated_title,
                    "source": resource.source,
                    "release_date": resource.release_date,
                }
            )
            # thumbnail url (small)
            # use file mtime as version token
            from pathlib import Path

            cover_dir = Path(settings.COVER_DIR)
            cover_path = None
            for ext in [".jpg", ".jpeg", ".png", ".webp"]:
                p = cover_dir / f"{avid}{ext}"
                if p.exists():
                    cover_path = p
                    break

            v = ""
            if cover_path and cover_path.exists():
                v = str(int(cover_path.stat().st_mtime))

            thumbnail_url = f"/nassav/api/resource/cover?avid={avid}&size=small"
            if v:
                thumbnail_url += f"&v={v}"

            return build_response(
                200, "success", {"metadata": metadata, "thumbnail_url": thumbnail_url}
            )
        except Exception as e:
            logger.error(f"生成 preview 失败: {e}")
            return build_response(500, f"生成 preview 失败: {e!s}", None)


class DownloadAbspathView(SchemaAPIView):
    """
    GET /api/downloads/abspath?avid=
    返回视频文件的绝对路径，并在前面拼接 config.FilePathPrefix 作为前缀
    """

    def get(self, request):
        avid = request.query_params.get("avid", "").upper()
        if not avid:
            return Response(
                {"code": 400, "message": "avid参数缺失", "data": None},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from pathlib import Path

        resource_dir = Path(settings.VIDEO_DIR)
        mp4_path = resource_dir / f"{avid}.mp4"

        if not mp4_path.exists():
            return build_response(404, f"视频 {avid} 不存在", None)

        try:
            abs_path = str(mp4_path.resolve())
        except Exception:
            abs_path = str(mp4_path.absolute())

        url_prefix = ""
        try:
            url_prefix = (
                settings.CONFIG.get("FilePathPrefix", "")
                if hasattr(settings, "CONFIG")
                else ""
            )
        except Exception:
            url_prefix = ""

        host_video_dir = getattr(settings, "VIDEO_HOST_DIR", None)
        if host_video_dir:
            abs_path = str(Path(host_video_dir) / mp4_path.name)

        # 拼接前缀和绝对路径
        prefixed = f"{url_prefix or ''}{abs_path}"

        return build_response(200, "success", {"abspath": prefixed})


class ResourceMetadataView(SchemaAPIView):
    """
    GET /api/resource/downloads/metadata?avid=
    根据avid获取视频元数据
    """

    def get(self, request):
        avid = request.query_params.get("avid", "").upper()
        if not avid:
            return Response(
                {"code": 400, "message": "avid参数缺失", "data": None},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from nassav.library_catalog import enabled, own_entry, project

        if enabled(request.user.pk):
            data = project(own_entry(request.user.pk, avid=avid), detail=True)
            data["duration"] = (
                f"{data['duration'] // 60}分钟" if data["duration"] else ""
            )
            response = build_response(200, "success", data)
            response["Cache-Control"] = "private, no-store"
            response["Vary"] = "Cookie"
            return response

        # 从数据库读取元数据
        try:
            from nassav.models import AVResource

            resource = AVResource.objects.filter(avid=avid).first()
            if not resource:
                return build_response(404, f"资源 {avid} 的元数据不存在", None)

            metadata = {
                "avid": resource.avid,
                "original_title": resource.original_title or "",
                "source_title": resource.source_title or "",
                "translated_title": resource.translated_title or "",
                "source": resource.source or "",
                "release_date": resource.release_date or "",
                "duration": f"{resource.duration // 60}分钟"
                if resource.duration
                else "",
                "director": "",
                "studio": "",
                "label": "",
                "series": "",
                "actors": [a.name for a in resource.actors.all()],
                "genres": [g.name for g in resource.genres.all()],
            }

            # 从 metadata JSON 补充额外字段（如 director, studio 等）
            if resource.metadata and isinstance(resource.metadata, dict):
                for key in ["director", "studio", "label", "series"]:
                    if resource.metadata.get(key):
                        metadata[key] = resource.metadata[key]

            # 添加文件信息
            metadata["file_exists"] = bool(resource.file_exists)
            metadata["file_size"] = resource.file_size if resource.file_size else None

            # Personal projection is request-owned; shared metadata timestamps cannot validate it.
            from nassav.personal_state import state_snapshot

            metadata.update(state_snapshot(resource, request.user.pk))
            # Conditional request handling: ETag + Last-Modified
            try:
                import json

                from nassav.utils import generate_etag_from_text

                etag = generate_etag_from_text(
                    json.dumps([request.user.pk, metadata], sort_keys=True)
                )
            except Exception:
                etag = '"0"'

            inm = request.headers.get("If-None-Match") or request.META.get(
                "HTTP_IF_NONE_MATCH"
            )

            # ETag match
            if inm and inm.strip() == etag:
                resp = Response(status=status.HTTP_304_NOT_MODIFIED)
                resp["ETag"] = etag
                resp["Cache-Control"] = "private, no-cache"
                resp["Vary"] = "Cookie"
                if resource.metadata_updated_at:
                    resp["Last-Modified"] = http_date(
                        resource.metadata_updated_at.timestamp()
                    )
                return resp

            resp = build_response(200, "success", metadata)
            resp["Cache-Control"] = "private, no-cache"
            resp["Vary"] = "Cookie"
            resp["ETag"] = etag
            if resource.metadata_updated_at:
                resp["Last-Modified"] = http_date(
                    resource.metadata_updated_at.timestamp()
                )
            return resp
        except Exception as e:
            logger.error(f"读取元数据失败: {e}")
            return build_response(500, f"读取元数据失败: {e!s}", None)
