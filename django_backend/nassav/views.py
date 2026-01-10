"""
API视图：实现资源管理接口
所有信息以 resource 目录中的实际资源为准
统一响应格式: {"code": xxx, "message": xxx, "data": data}
"""
import json

from django.conf import settings
from django.http import FileResponse
from django.urls import reverse
from django.utils.http import http_date
from loguru import logger
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .api_utils import build_response
from .serializers import (
    NewResourceSerializer,
    SourceCookieListSerializer,
    SourceCookieSerializer,
    UserSettingSerializer,
    UserSettingUpdateSerializer,
)
from .services import list_resources, source_manager
from .utils import (
    generate_etag_for_file,
    generate_thumbnail,
    parse_http_if_modified_since,
)


def _serialize_resource_obj(resource):
    """Convert AVResource instance to plain dict suitable for API responses."""
    try:
        actors = [a.name for a in resource.actors.all()]
    except Exception:
        actors = []
    try:
        genres = [g.name for g in resource.genres.all()]
    except Exception:
        genres = []

    return {
        "avid": resource.avid,
        "original_title": resource.original_title or "",
        "source_title": resource.source_title or "",
        "translated_title": resource.translated_title or "",
        "m3u8": resource.m3u8 or "",
        "source": resource.source or "",
        "release_date": resource.release_date or "",
        "duration": resource.duration,
        "actors": actors,
        "genres": genres,
        "file_size": resource.file_size,
        "file_exists": bool(resource.file_exists),
        "watched": bool(resource.watched),
        "is_favorite": bool(resource.is_favorite),
    }


class SourceListView(APIView):
    """
    GET /api/source/list
    获取所有可用的下载源名称列表
    """

    def get(self, request):
        sources = list(source_manager.sources.keys())
        return Response({"code": 200, "message": "success", "data": sources})


class SourceCookieView(APIView):
    """
    GET /api/source/cookie
    获取所有源的 Cookie 列表。

    POST /api/source/cookie
    设置或自动获取指定源的 Cookie。

    DELETE /api/source/cookie?source=xxx
    清除指定源的 Cookie。

    Request JSON (POST):
      - source: 源名称 (required)
      - cookie: 手动设置的 cookie (optional)
      - auto: 是否自动获取 cookie (boolean, optional)
    """

    def get(self, request):
        """获取所有源的 Cookie 配置"""
        from .models import SourceCookie

        cookies = SourceCookie.objects.all().order_by("source_name")
        serializer = SourceCookieListSerializer(cookies, many=True)
        return Response({"code": 200, "message": "success", "data": serializer.data})

    def post(self, request):
        data = request.data or {}
        source_name = data.get("source")
        cookie = data.get("cookie")
        auto = data.get("auto", False)

        if not source_name:
            return Response(
                {"code": 400, "message": "source 参数缺失", "data": None},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 如果请求自动获取 cookie
        if auto:
            try:
                # 找到对应的 source 实例并尝试自动获取 cookie
                source_instance = None
                for name, inst in source_manager.sources.items():
                    if name.lower() == source_name.lower():
                        source_instance = inst
                        break

                if not source_instance:
                    return Response(
                        {
                            "code": 404,
                            "message": f"无法获取 {source_name} 实例",
                            "data": None,
                        },
                        status=status.HTTP_404_NOT_FOUND,
                    )

                success = False
                try:
                    success = source_instance.set_cookie_auto(force_refresh=True)
                except Exception as e:
                    logger.error(f"自动获取 Cookie 失败: {e}")

                if success:
                    return Response(
                        {
                            "code": 200,
                            "message": "Cookie 自动获取成功",
                            "data": {"source": source_name, "cookie_set": True},
                        }
                    )
                else:
                    return Response(
                        {"code": 500, "message": "Cookie 自动获取失败", "data": None},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    )
            except Exception as e:
                logger.error(f"自动获取 Cookie 异常: {e}")
                return Response(
                    {"code": 500, "message": f"自动获取 Cookie 异常: {str(e)}", "data": None},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

        # 否则如果提供了 cookie 则手动设置并保存到 DB
        if cookie:
            success = source_manager.set_source_cookie(source_name, cookie)
            if success:
                return Response(
                    {
                        "code": 200,
                        "message": "success",
                        "data": {
                            "source": source_name,
                            "cookie_set": True,
                            "auto_fetched": False,
                        },
                    }
                )
            else:
                return Response(
                    {"code": 500, "message": "设置 Cookie 失败", "data": None},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

        return Response(
            {"code": 400, "message": "未提供 cookie 且 auto 未设置为 True", "data": None},
            status=status.HTTP_400_BAD_REQUEST,
        )

    def delete(self, request):
        """删除指定源的 Cookie（设为空）"""
        source_name = request.query_params.get("source")
        if not source_name:
            return Response(
                {"code": 400, "message": "source 参数缺失", "data": None},
                status=status.HTTP_400_BAD_REQUEST,
            )

        success = source_manager.set_source_cookie(source_name, "")
        if success:
            return Response(
                {
                    "code": 200,
                    "message": "Cookie 已清除",
                    "data": {"source": source_name, "cookie_set": False},
                }
            )
        else:
            return Response(
                {"code": 500, "message": "清除 Cookie 失败", "data": None},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class UserSettingView(APIView):
    """
    GET /api/setting
    获取用户设置。

    PUT /api/setting
    更新用户设置。
    """

    def get(self, request):
        """获取所有用户设置"""
        from nassav.user_settings import get_settings_manager

        try:
            settings_manager = get_settings_manager()
            settings = settings_manager.get_all()
            serializer = UserSettingSerializer(settings)
            return Response(
                {"code": 200, "message": "success", "data": serializer.data}
            )
        except Exception as e:
            logger.error(f"获取用户设置失败: {e}")
            return Response(
                {"code": 500, "message": f"获取设置失败: {str(e)}", "data": None},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def put(self, request):
        """更新用户设置"""
        from nassav.user_settings import get_settings_manager

        serializer = UserSettingUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"code": 400, "message": "参数验证失败", "data": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            settings_manager = get_settings_manager()
            results = settings_manager.update_batch(serializer.validated_data)

            # 检查是否有更新失败的项
            failed = {k: v for k, v in results.items() if not v}
            if failed:
                return Response(
                    {
                        "code": 500,
                        "message": "部分设置更新失败",
                        "data": {"failed": list(failed.keys())},
                    },
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

            # 返回更新后的所有设置
            updated_settings = settings_manager.get_all()
            return Response(
                {
                    "code": 200,
                    "message": "设置已更新",
                    "data": UserSettingSerializer(updated_settings).data,
                }
            )
        except Exception as e:
            logger.error(f"更新用户设置失败: {e}")
            return Response(
                {"code": 500, "message": f"更新设置失败: {str(e)}", "data": None},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class ResourcesListView(APIView):
    """GET /api/resources/ - consolidated resource listing with filters/pagination"""

    def get(self, request):
        # support legacy sort_by / order params from older endpoints
        params = request.query_params.copy()
        sort_by = params.get("sort_by")
        order = params.get("order", "desc")
        if sort_by:
            sort_map = {
                "avid": "avid",
                "metadata_create_time": "metadata_created_at",
                "metadata_update_time": "metadata_updated_at",
                "video_create_time": "video_saved_at",
                "source": "source",
            }
            sort_field = sort_map.get(sort_by, None)
            if sort_field:
                if order == "desc":
                    params["ordering"] = f"-{sort_field}"
                else:
                    params["ordering"] = sort_field

        objs, pagination = list_resources(params)
        # reuse ResourceSummarySerializer
        from .serializers import ResourceSummarySerializer

        serializer = ResourceSummarySerializer(objs, many=True)

        # return standardized envelope with pagination field
        return build_response(200, "success", serializer.data, pagination=pagination)


class ActorsListView(APIView):
    """GET /api/actors/ - 返回演员列表及每个演员的作品数，支持分页"""

    def get(self, request):
        from django.core.paginator import Paginator
        from django.db.models import Count
        from nassav.constants import ACTOR_AVATAR_PLACEHOLDER_URLS
        from nassav.models import Actor

        # 获取参数
        page = int(request.query_params.get("page", 1))
        page_size = int(request.query_params.get("page_size", 20))
        order_by = request.query_params.get("order_by", "count")
        order = request.query_params.get("order", "desc")
        search = request.query_params.get("search", "").strip()
        actor_id = request.query_params.get("id", "").strip()

        # 构建查询
        qs = Actor.objects.annotate(resource_count=Count("resources"))

        # 过滤掉没有关联资源的演员（除非明确指定 ID）
        if not actor_id:
            qs = qs.filter(resource_count__gt=0)

        # ID 过滤（精确匹配）
        if actor_id:
            try:
                aid = int(actor_id)
                qs = qs.filter(id=aid)
            except ValueError:
                pass

        # 搜索过滤
        if search:
            qs = qs.filter(name__icontains=search)

        # 排序
        if order_by == "name":
            qs = qs.order_by("name" if order == "asc" else "-name")
        else:  # count
            if order == "desc":
                qs = qs.order_by("-resource_count", "name")
            else:
                qs = qs.order_by("resource_count", "name")

        # 分页
        paginator = Paginator(qs, page_size)
        page_obj = paginator.get_page(page)

        data = [
            {
                "id": a.id,
                "name": a.name,
                "resource_count": getattr(a, "resource_count", 0),
                "avatar_url": a.avatar_url
                if a.avatar_url not in ACTOR_AVATAR_PLACEHOLDER_URLS
                else None,
                "avatar_filename": a.avatar_filename
                if a.avatar_url not in ACTOR_AVATAR_PLACEHOLDER_URLS
                else None,
            }
            for a in page_obj.object_list
        ]

        pagination = {
            "total": paginator.count,
            "page": page_obj.number,
            "page_size": page_size,
            "pages": paginator.num_pages,
        }

        return build_response(200, "success", data, pagination=pagination)


class ActorAvatarView(APIView):
    """GET /api/actors/<int:actor_id>/avatar - 返回演员头像图片"""

    def get(self, request, actor_id):
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


class GenresListView(APIView):
    """GET /api/genres/ - 返回类别列表及每个类别的作品数，支持分页"""

    def get(self, request):
        from django.core.paginator import Paginator
        from django.db.models import Count
        from nassav.models import Genre

        # 获取参数
        page = int(request.query_params.get("page", 1))
        page_size = int(request.query_params.get("page_size", 20))
        order_by = request.query_params.get("order_by", "count")
        order = request.query_params.get("order", "desc")
        search = request.query_params.get("search", "").strip()
        genre_id = request.query_params.get("id", "").strip()

        # 构建查询
        qs = Genre.objects.annotate(resource_count=Count("resources"))

        # 过滤掉没有关联资源的类别（除非明确指定 ID）
        if not genre_id:
            qs = qs.filter(resource_count__gt=0)

        # ID 过滤（精确匹配）
        if genre_id:
            try:
                gid = int(genre_id)
                qs = qs.filter(id=gid)
            except ValueError:
                pass

        # 搜索过滤
        if search:
            qs = qs.filter(name__icontains=search)

        # 排序
        if order_by == "name":
            qs = qs.order_by("name" if order == "asc" else "-name")
        else:  # count
            if order == "desc":
                qs = qs.order_by("-resource_count", "name")
            else:
                qs = qs.order_by("resource_count", "name")

        # 分页
        paginator = Paginator(qs, page_size)
        page_obj = paginator.get_page(page)

        data = [
            {
                "id": g.id,
                "name": g.name,
                "resource_count": getattr(g, "resource_count", 0),
            }
            for g in page_obj.object_list
        ]

        pagination = {
            "total": paginator.count,
            "page": page_obj.number,
            "page_size": page_size,
            "pages": paginator.num_pages,
        }

        return build_response(200, "success", data, pagination=pagination)


class ResourceCoverView(APIView):
    """
    GET /api/resource/cover?avid=
    根据avid获取封面图片
    """

    def get(self, request):
        avid = request.query_params.get("avid", "").upper()
        if not avid:
            return build_response(400, "avid参数缺失", None)
        # 支持 size 参数：small|medium|large（保存到 COVER_DIR/thumbnails/{size}/{avid}.jpg）
        import mimetypes
        from pathlib import Path

        size = request.query_params.get("size")

        cover_dir = Path(settings.COVER_DIR)
        # find original cover (any extension)
        cover_path = None
        for ext in [".jpg", ".jpeg", ".png", ".webp"]:
            p = cover_dir / f"{avid}{ext}"
            if p.exists():
                cover_path = p
                break

        if not cover_path:
            return Response(
                {"code": 404, "message": f"封面 {avid} 不存在", "data": None},
                status=status.HTTP_404_NOT_FOUND,
            )

        # if no size requested, return original file (with conditional handling)
        if not size:
            ctype, _ = mimetypes.guess_type(str(cover_path))
            if not ctype:
                ctype = "application/octet-stream"
            # ETag + Last-Modified
            try:
                etag = generate_etag_for_file(cover_path)
            except Exception:
                etag = '"0"'

            ims = request.headers.get("If-Modified-Since") or request.META.get(
                "HTTP_IF_MODIFIED_SINCE"
            )
            inm = request.headers.get("If-None-Match") or request.META.get(
                "HTTP_IF_NONE_MATCH"
            )
            # check ETag
            if inm and etag and inm.strip() == etag:
                resp = Response(status=status.HTTP_304_NOT_MODIFIED)
                resp["ETag"] = etag
                resp["Last-Modified"] = http_date(cover_path.stat().st_mtime)
                return resp
            # check If-Modified-Since
            ims_ts = parse_http_if_modified_since(ims)
            if ims_ts is not None and int(cover_path.stat().st_mtime) <= ims_ts:
                resp = Response(status=status.HTTP_304_NOT_MODIFIED)
                resp["ETag"] = etag
                resp["Last-Modified"] = http_date(cover_path.stat().st_mtime)
                return resp

            resp = FileResponse(
                open(cover_path, "rb"), content_type=ctype, as_attachment=False
            )
            # Cache long
            resp["Cache-Control"] = "public, max-age=31536000"
            resp["ETag"] = etag
            resp["Last-Modified"] = http_date(cover_path.stat().st_mtime)
            return resp

        size = str(size).lower()
        sizes_map = {"small": 200, "medium": 600, "large": 1200}
        if size not in sizes_map:
            return build_response(400, "size 参数无效，支持 small|medium|large", None)

        thumb_dir = Path(
            getattr(settings, "THUMBNAIL_DIR", settings.COVER_DIR / "thumbnails")
        )
        thumb_path = thumb_dir / size / f"{avid}.jpg"

        # if thumbnail exists and up-to-date, serve it
        try:
            if (
                thumb_path.exists()
                and thumb_path.stat().st_mtime >= cover_path.stat().st_mtime
            ):
                # Conditional checks
                etag = generate_etag_for_file(thumb_path)
                inm = request.headers.get("If-None-Match") or request.META.get(
                    "HTTP_IF_NONE_MATCH"
                )
                ims = request.headers.get("If-Modified-Since") or request.META.get(
                    "HTTP_IF_MODIFIED_SINCE"
                )
                if inm and inm.strip() == etag:
                    resp = Response(status=status.HTTP_304_NOT_MODIFIED)
                    resp["ETag"] = etag
                    resp["Last-Modified"] = http_date(thumb_path.stat().st_mtime)
                    return resp
                ims_ts = parse_http_if_modified_since(ims)
                if ims_ts is not None and int(thumb_path.stat().st_mtime) <= ims_ts:
                    resp = Response(status=status.HTTP_304_NOT_MODIFIED)
                    resp["ETag"] = etag
                    resp["Last-Modified"] = http_date(thumb_path.stat().st_mtime)
                    return resp

                resp = FileResponse(
                    open(thumb_path, "rb"),
                    content_type="image/jpeg",
                    as_attachment=False,
                )
                resp["Cache-Control"] = "public, max-age=31536000"
                resp["ETag"] = etag
                resp["Last-Modified"] = http_date(thumb_path.stat().st_mtime)
                return resp
        except Exception:
            pass

        # try to generate thumbnail (best-effort)
        success = generate_thumbnail(cover_path, thumb_path, sizes_map[size])
        if success and thumb_path.exists():
            resp = FileResponse(
                open(thumb_path, "rb"), content_type="image/jpeg", as_attachment=False
            )
            resp["Cache-Control"] = "public, max-age=31536000"
            resp["Last-Modified"] = http_date(thumb_path.stat().st_mtime)
            return resp

        # fallback: return original
        ctype, _ = mimetypes.guess_type(str(cover_path))
        if not ctype:
            ctype = "application/octet-stream"
        resp = FileResponse(
            open(cover_path, "rb"), content_type=ctype, as_attachment=False
        )
        resp["Cache-Control"] = "public, max-age=31536000"
        resp["Last-Modified"] = http_date(cover_path.stat().st_mtime)
        return resp


class ResourcePreviewView(APIView):
    """GET /api/resource/{avid}/preview - 返回 metadata + thumbnail_url（small 默认为首屏预览）"""

    def get(self, request, avid):
        avid = avid.upper()
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
            return build_response(500, f"生成 preview 失败: {str(e)}", None)


class DownloadAbspathView(APIView):
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

        # 拼接前缀和绝对路径
        prefixed = f"{url_prefix}{abs_path}"

        return build_response(200, "success", {"abspath": prefixed})


class ResourceMetadataView(APIView):
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
                "duration": f"{resource.duration // 60}分钟" if resource.duration else "",
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

            # 添加观看和收藏状态
            metadata["watched"] = bool(resource.watched)
            metadata["is_favorite"] = bool(resource.is_favorite)

            # Conditional request handling: ETag + Last-Modified
            try:
                import json

                from .utils import generate_etag_from_text

                etag = generate_etag_from_text(json.dumps(metadata, sort_keys=True))
            except Exception:
                etag = '"0"'

            ims = request.headers.get("If-Modified-Since") or request.META.get(
                "HTTP_IF_MODIFIED_SINCE"
            )
            inm = request.headers.get("If-None-Match") or request.META.get(
                "HTTP_IF_NONE_MATCH"
            )

            # ETag match
            if inm and inm.strip() == etag:
                resp = Response(status=status.HTTP_304_NOT_MODIFIED)
                resp["ETag"] = etag
                if resource.metadata_updated_at:
                    resp["Last-Modified"] = http_date(
                        resource.metadata_updated_at.timestamp()
                    )
                return resp

            # If-Modified-Since match
            ims_ts = parse_http_if_modified_since(ims)
            if (
                ims_ts is not None
                and resource.metadata_updated_at
                and int(resource.metadata_updated_at.timestamp()) <= ims_ts
            ):
                resp = Response(status=status.HTTP_304_NOT_MODIFIED)
                resp["ETag"] = etag
                resp["Last-Modified"] = http_date(
                    resource.metadata_updated_at.timestamp()
                )
                return resp

            resp = build_response(200, "success", metadata)
            resp["ETag"] = etag
            if resource.metadata_updated_at:
                resp["Last-Modified"] = http_date(
                    resource.metadata_updated_at.timestamp()
                )
            return resp
        except Exception as e:
            logger.error(f"读取元数据失败: {e}")
            return build_response(500, f"读取元数据失败: {str(e)}", None)


class ResourceView(APIView):
    """
    POST /api/resource/new
    通过avid获取资源信息并保存（HTML、封面、元数据）

    请求参数:
        avid: 视频编号
        downloader: 指定源名称，默认 "any" 表示尝试所有源
    """

    def post(self, request):
        from nassav.resource_service import (
            ResourceAccessDeniedError,
            ResourceAlreadyExistsError,
            ResourceFetchError,
            ResourceNotFoundError,
            resource_service,
        )

        serializer = NewResourceSerializer(data=request.data)
        if not serializer.is_valid():
            return build_response(400, "参数错误", serializer.errors)

        avid = serializer.validated_data["avid"].upper()
        source = serializer.validated_data.get("source", "any").lower()

        # 检查指定源是否存在
        if source != "any":
            available_sources = [s.lower() for s in source_manager.sources.keys()]
            if source not in available_sources:
                return build_response(
                    400,
                    f"源 {source} 不存在",
                    {"available_sources": list(source_manager.sources.keys())},
                )

        # 调用ResourceService添加资源
        try:
            result = resource_service.add_resource(avid, source)

            # 记录封面下载失败警告
            if not result["cover_saved"]:
                logger.warning(f"封面下载失败: {avid}")

            # 只返回指定的字段
            resource_data = result["resource"]
            filtered_resource = {
                "avid": resource_data.get("avid"),
                "original_title": resource_data.get("original_title"),
                "source_title": resource_data.get("source_title"),
                "translated_title": resource_data.get("translated_title"),
                "source": resource_data.get("source"),
            }

            return build_response(
                201,
                "success",
                {
                    "resource": filtered_resource,
                    "cover_downloaded": result["cover_saved"],
                    "metadata_saved": result["metadata_saved"],
                    "scraped": result["scraped"],
                },
            )

        except ResourceAlreadyExistsError as e:
            # 409 Conflict - 资源已存在
            # 只返回指定的字段
            filtered_resource = {
                "avid": e.resource_data.get("avid"),
                "original_title": e.resource_data.get("original_title"),
                "source_title": e.resource_data.get("source_title"),
                "translated_title": e.resource_data.get("translated_title"),
                "source": e.resource_data.get("source"),
            }
            return build_response(409, str(e), filtered_resource)

        except ResourceNotFoundError as e:
            # 404 Not Found - 所有源都返回404
            return build_response(404, str(e), None)

        except ResourceAccessDeniedError as e:
            # 403 Forbidden - 有源返回403
            return build_response(403, str(e), None)

        except ResourceFetchError as e:
            # 502 Bad Gateway - 网络错误
            return build_response(502, str(e), None)

        except Exception as e:
            # 500 Internal Server Error - 未预期的错误
            logger.error(f"添加资源失败: {avid}, 错误: {e}", exc_info=True)
            return build_response(500, f"服务器内部错误: {str(e)}", None)

        # (clean) end of ResourceView.post


class DownloadView(APIView):
    def post(self, request, avid):
        """
        POST /api/resource/downloads
        通过avid下载视频，此avid的元数据必须已存在于 resource 目录中
        """
        avid = avid.upper()

        # 检查元数据是否存在（数据库）
        try:
            from nassav.models import AVResource

            resource = AVResource.objects.filter(avid=avid).first()
            if not resource:
                return build_response(
                    404, f"{avid} 的元数据不存在，请先调用 /api/resource/new 添加资源", None
                )

            # 检查是否已下载
            if resource.file_exists:
                return build_response(
                    409,
                    "视频已下载",
                    {
                        "avid": avid,
                        "task_id": None,
                        "status": "completed",
                        "file_size": resource.file_size,
                    },
                )
        except Exception:
            return Response(
                {"code": 500, "message": "服务器内部错误", "data": None},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # 使用Celery异步下载（带去重检查）
        from .tasks import submit_download_task

        task_result, is_duplicate = submit_download_task(avid)

        if is_duplicate:
            return build_response(409, "下载任务已存在", None)

        task = task_result

        return build_response(
            202,
            "下载任务已提交",
            {"avid": avid, "task_id": task.id, "status": "pending", "file_size": None},
        )

    def delete(self, request, avid):
        """
        DELETE /api/downloads/{avid}
        删除已下载的视频文件
        """
        avid = avid.upper()
        from pathlib import Path

        mp4_path = Path(settings.VIDEO_DIR) / f"{avid}.mp4"

        if not mp4_path.exists():
            return build_response(404, f"视频 {avid} 不存在", None)

        try:
            file_size = mp4_path.stat().st_size
            mp4_path.unlink()
            try:
                from nassav.models import AVResource

                AVResource.objects.filter(avid=avid).update(
                    file_exists=False, file_size=None, video_saved_at=None
                )
            except Exception as e:
                logger.warning(f"删除 mp4 后更新 DB 失败: {e}")
            logger.info(f"已删除视频: {avid}")
            return build_response(
                200,
                "success",
                {"avid": avid, "deleted_file": f"{avid}.mp4", "file_size": file_size},
            )
        except Exception as e:
            logger.error(f"删除视频失败: {e}")
            return build_response(500, f"删除失败: {str(e)}", None)


class RefreshResourceView(APIView):
    """
    POST /api/resource/refresh/{avid}
    刷新已有资源的元数据和m3u8链接，使用原有source获取

    支持细粒度刷新参数：
    - refresh_m3u8: 是否刷新 m3u8 链接（默认 true）
    - refresh_metadata: 是否刷新元数据（默认 true）
    - retranslate: 是否重新翻译标题（默认 false）

    注意：当同时刷新元数据和重新翻译时，会先刷新元数据获取新标题，再执行翻译
    """

    def post(self, request, avid):
        from nassav.resource_service import (
            ResourceNotFoundError,
            resource_service,
        )

        avid = avid.upper()

        # 解析参数，默认全部刷新
        refresh_m3u8 = request.data.get("refresh_m3u8", True)
        refresh_metadata = request.data.get("refresh_metadata", True)
        retranslate = request.data.get("retranslate", False)

        result_info = {}

        # 刷新元数据和/或 m3u8
        if refresh_metadata or refresh_m3u8:
            try:
                # 使用ResourceService刷新资源
                refresh_result = resource_service.refresh_resource(
                    avid, scrape=refresh_metadata, download_cover=refresh_metadata
                )

                result_info["cover_downloaded"] = refresh_result["cover_saved"]
                result_info["metadata_saved"] = refresh_result["metadata_saved"]
                result_info["scraped"] = refresh_result.get("scraped", False)
                result_info["metadata_refreshed"] = refresh_metadata
                result_info["m3u8_refreshed"] = refresh_m3u8
                result_info["m3u8_updated"] = refresh_result.get("m3u8_updated", False)

            except ResourceNotFoundError as e:
                # 资源不存在于数据库中
                return build_response(404, str(e), None)

            except Exception as e:
                # 其他错误
                logger.error(f"刷新资源失败: {avid}, 错误: {e}", exc_info=True)
                return build_response(500, f"刷新失败: {str(e)}", None)

        # 重新翻译（必须在元数据刷新之后执行，确保使用最新的标题）
        if retranslate:
            try:
                from nassav.models import AVResource
                from nassav.tasks import translate_title_task

                # 重新加载 resource 以获取最新的 title
                resource = AVResource.objects.filter(avid=avid).first()
                if not resource:
                    return build_response(404, f"{avid} 的资源不存在", None)

                resource.refresh_from_db()

                # 重置翻译状态并提交翻译任务
                resource.translation_status = "pending"
                resource.translated_title = None
                resource.save(update_fields=["translation_status", "translated_title"])

                # 异步翻译
                translate_title_task.delay(avid)
                result_info["translation_queued"] = True
                logger.info(f"已提交 {avid} 的翻译任务")
            except Exception as e:
                logger.error(f"提交翻译任务失败: {e}")
                result_info["translation_error"] = str(e)

        # 返回刷新后的资源对象，便于前端局部刷新
        try:
            from nassav.models import AVResource

            resource = AVResource.objects.filter(avid=avid).first()
            if resource:
                resource.refresh_from_db()
                resource_data = _serialize_resource_obj(resource)
            else:
                resource_data = None
        except Exception as e:
            logger.error(f"序列化资源对象失败: {e}")
            resource_data = None

        result_info["resource"] = resource_data
        return build_response(200, "success", result_info)


class DeleteResourceView(APIView):
    """
    DELETE /api/resource/{avid}
    删除整个资源目录（包括 HTML、封面、元数据、视频）
    """

    def delete(self, request, avid):
        import shutil

        avid = avid.upper()
        from pathlib import Path

        cover_root = Path(settings.COVER_DIR)
        video_root = Path(settings.VIDEO_DIR)
        backup_root = Path(
            getattr(
                settings,
                "RESOURCE_BACKUP_DIR",
                Path(settings.BASE_DIR) / "resource_backup",
            )
        )
        thumbnail_root = Path(
            getattr(settings, "THUMBNAIL_DIR", cover_root / "thumbnails")
        )

        cover_candidates = []
        for ext in [".jpg", ".jpeg", ".png", ".webp"]:
            p = cover_root / f"{avid}{ext}"
            if p.exists():
                cover_candidates.append(p)

        # 收集所有尺寸的缩略图
        thumbnail_candidates = []
        for size in ["small", "medium", "large"]:
            thumb_path = thumbnail_root / size / f"{avid}.jpg"
            if thumb_path.exists():
                thumbnail_candidates.append(thumb_path)

        mp4_path = video_root / f"{avid}.mp4"
        backup_dir = backup_root / avid

        if (
            not cover_candidates
            and not thumbnail_candidates
            and not mp4_path.exists()
            and not backup_dir.exists()
        ):
            return build_response(404, f"资源 {avid} 不存在", None)

        try:
            deleted_files = []
            for p in cover_candidates:
                deleted_files.append(p.name)
                try:
                    p.unlink()
                except Exception:
                    pass

            # 删除所有尺寸的缩略图
            for p in thumbnail_candidates:
                deleted_files.append(f"thumbnail/{p.parent.name}/{p.name}")
                try:
                    p.unlink()
                except Exception:
                    pass

            if mp4_path.exists():
                deleted_files.append(mp4_path.name)
                try:
                    mp4_path.unlink()
                except Exception:
                    pass

            # 删除备份旧目录（若存在）
            if backup_dir.exists():
                try:
                    for f in backup_dir.iterdir():
                        deleted_files.append(f.name)
                    shutil.rmtree(backup_dir)
                except Exception:
                    pass

            # 同步删除数据库中的记录（若存在）；在删除前尝试序列化对象以便返回
            resource_data = None
            try:
                from nassav.models import AVResource

                resource_obj = AVResource.objects.filter(avid=avid).first()
                if resource_obj:
                    resource_data = _serialize_resource_obj(resource_obj)
                AVResource.objects.filter(avid=avid).delete()
            except Exception as e:
                logger.warning(f"删除数据库记录失败: {e}")

            logger.info(f"已删除资源: {avid}")
            return build_response(
                200,
                "success",
                {
                    "resource": resource_data,
                    "avid": avid,
                    "deleted_files": deleted_files,
                },
            )
        except Exception as e:
            logger.error(f"删除资源失败: {e}")
            return build_response(500, f"删除失败: {str(e)}", None)


class TaskQueueStatusView(APIView):
    """
    GET /api/tasks/queue/status
    获取当前任务队列状态

    返回完整的任务队列列表（从 Redis 获取），包括所有 PENDING 和 STARTED 状态的任务。
    解决了 Celery inspect() 只能获取部分任务的限制问题。
    """

    def get(self, request):
        from .tasks import get_full_task_queue

        try:
            queue_status = get_full_task_queue()
            return build_response(200, "success", queue_status)
        except Exception as e:
            logger.error(f"获取任务队列状态失败: {e}")
            return build_response(500, f"获取队列状态失败: {str(e)}", None)


class ResourcesBatchView(APIView):
    """POST /api/resources/batch

    Body example:
      { "actions": [ {"action":"add","avid":"ABC-123","source":"any"},
                      {"action":"delete-video","avid":"XYZ-001"},
                      {"action":"delete-all","avid":"OLD-999"},
                      {"action":"refresh","avid":"DEF-222"} ] }

    支持的 action 类型：
    - add: 添加资源
    - refresh: 刷新资源元数据和 m3u8
    - delete-video: 只删除视频文件，保留元数据
    - delete-all 或 delete: 删除全部数据（视频+元数据+封面+备份）
    """

    def post(self, request):
        import time

        data = request.data or {}
        actions = data.get("actions") or []
        results = []

        for act in actions:
            action = (act.get("action") or "").lower()
            avid = (act.get("avid") or "").upper()
            if not avid:
                results.append(
                    {
                        "action": action,
                        "avid": None,
                        "code": 400,
                        "message": "avid 缺失",
                        "resource": None,
                    }
                )
                continue

            try:
                if action == "add":
                    # 先检查资源是否已存在
                    from nassav.models import AVResource

                    existing_resource = AVResource.objects.filter(avid=avid).first()

                    if existing_resource:
                        # 资源已存在，返回现有数据
                        resource_data = _serialize_resource_obj(existing_resource)
                        results.append(
                            {
                                "action": "add",
                                "avid": avid,
                                "code": 200,
                                "message": "already exists",
                                "resource": resource_data,
                            }
                        )
                        continue

                    # 资源不存在，执行添加操作
                    source = (act.get("source") or "any").lower()
                    time.sleep(2)

                    # 使用ResourceService添加资源
                    try:
                        from nassav.resource_service import (
                            ResourceAccessDeniedError,
                            ResourceAlreadyExistsError,
                            ResourceFetchError,
                            ResourceNotFoundError,
                            resource_service,
                        )

                        result = resource_service.add_resource(avid, source)
                        results.append(
                            {
                                "action": "add",
                                "avid": avid,
                                "code": 201,
                                "message": "created",
                                "resource": result["resource"],
                            }
                        )

                    except ResourceAlreadyExistsError as e:
                        # 资源已存在(理论上不应该到这里,因为前面已经检查过)
                        results.append(
                            {
                                "action": "add",
                                "avid": avid,
                                "code": 200,
                                "message": "already exists",
                                "resource": e.resource_data,
                            }
                        )

                    except ResourceNotFoundError as e:
                        results.append(
                            {
                                "action": "add",
                                "avid": avid,
                                "code": 404,
                                "message": str(e),
                                "resource": None,
                            }
                        )

                    except ResourceAccessDeniedError as e:
                        results.append(
                            {
                                "action": "add",
                                "avid": avid,
                                "code": 403,
                                "message": str(e),
                                "resource": None,
                            }
                        )

                    except ResourceFetchError as e:
                        results.append(
                            {
                                "action": "add",
                                "avid": avid,
                                "code": 502,
                                "message": str(e),
                                "resource": None,
                            }
                        )

                    except Exception as e:
                        logger.error(f"批量添加资源失败: {avid}, 错误: {e}", exc_info=True)
                        results.append(
                            {
                                "action": "add",
                                "avid": avid,
                                "code": 500,
                                "message": f"服务器内部错误: {str(e)}",
                                "resource": None,
                            }
                        )

                elif action == "delete-video":
                    # 只删除视频文件，保留元数据
                    from pathlib import Path

                    mp4_path = Path(settings.VIDEO_DIR) / f"{avid}.mp4"

                    if not mp4_path.exists():
                        results.append(
                            {
                                "action": "delete-video",
                                "avid": avid,
                                "code": 404,
                                "message": "视频不存在",
                                "resource": None,
                            }
                        )
                        continue

                    try:
                        file_size = mp4_path.stat().st_size
                        mp4_path.unlink()
                        logger.info(f"已删除视频: {avid}")
                        # 更新数据库记录，标记视频不存在
                        from nassav.models import AVResource

                        AVResource.objects.filter(avid=avid).update(
                            file_exists=False, file_size=None, video_saved_at=None
                        )
                        logger.info(f"已删除视频: {avid}")
                        results.append(
                            {
                                "action": "delete-video",
                                "avid": avid,
                                "code": 200,
                                "message": "视频已删除",
                                "deleted_file": f"{avid}.mp4",
                                "file_size": file_size,
                            }
                        )
                    except Exception as e:
                        logger.error(f"删除视频失败: {e}")
                        results.append(
                            {
                                "action": "delete-video",
                                "avid": avid,
                                "code": 500,
                                "message": f"删除失败: {str(e)}",
                                "resource": None,
                            }
                        )

                elif action in ["delete", "delete-all"]:
                    # 删除全部数据（视频+元数据+封面+备份）
                    import shutil
                    from pathlib import Path

                    cover_root = Path(settings.COVER_DIR)
                    video_root = Path(settings.VIDEO_DIR)
                    backup_root = Path(
                        getattr(
                            settings,
                            "RESOURCE_BACKUP_DIR",
                            Path(settings.BASE_DIR) / "resource_backup",
                        )
                    )

                    cover_candidates = []
                    for ext in [".jpg", ".jpeg", ".png", ".webp"]:
                        p = cover_root / f"{avid}{ext}"
                        if p.exists():
                            cover_candidates.append(p)

                    mp4_path = video_root / f"{avid}.mp4"
                    backup_dir = backup_root / avid

                    if (
                        not cover_candidates
                        and not mp4_path.exists()
                        and not backup_dir.exists()
                    ):
                        results.append(
                            {
                                "action": action,
                                "avid": avid,
                                "code": 404,
                                "message": "资源不存在",
                                "resource": None,
                            }
                        )
                        continue

                    deleted_files = []
                    for p in cover_candidates:
                        deleted_files.append(p.name)
                        try:
                            p.unlink()
                            logger.info(f"已删除封面: {p.name}")
                        except Exception:
                            pass

                    if mp4_path.exists():
                        deleted_files.append(mp4_path.name)
                        logger.info(f"已删除视频: {mp4_path.name}")
                        try:
                            mp4_path.unlink()
                        except Exception:
                            pass

                    if backup_dir.exists():
                        try:
                            for f in backup_dir.iterdir():
                                deleted_files.append(f.name)
                            shutil.rmtree(backup_dir)
                        except Exception:
                            pass

                    # serialize and delete DB record
                    from nassav.models import AVResource

                    resource_data = None
                    try:
                        resource_obj = AVResource.objects.filter(avid=avid).first()
                        if resource_obj:
                            resource_data = _serialize_resource_obj(resource_obj)
                        AVResource.objects.filter(avid=avid).delete()
                    except Exception:
                        pass

                    results.append(
                        {
                            "action": action,
                            "avid": avid,
                            "code": 200,
                            "message": "已删除全部数据",
                            "resource": resource_data,
                            "deleted_files": deleted_files,
                        }
                    )

                elif action == "refresh":
                    # 支持细粒度刷新参数
                    from nassav.models import AVResource

                    resource = AVResource.objects.filter(avid=avid).first()
                    if not resource:
                        results.append(
                            {
                                "action": "refresh",
                                "avid": avid,
                                "code": 404,
                                "message": "资源不存在",
                                "resource": None,
                            }
                        )
                        continue
                    source = resource.source or ""
                    if not source:
                        results.append(
                            {
                                "action": "refresh",
                                "avid": avid,
                                "code": 400,
                                "message": "没有 source 信息",
                                "resource": None,
                            }
                        )
                        continue

                    # 解析细粒度参数
                    refresh_m3u8 = act.get("refresh_m3u8", True)
                    refresh_metadata = act.get("refresh_metadata", True)
                    retranslate = act.get("retranslate", False)

                    refresh_info = {}

                    # 刷新元数据和/或 m3u8
                    if refresh_metadata or refresh_m3u8:
                        try:
                            from nassav.resource_service import (
                                ResourceNotFoundError,
                                resource_service,
                            )

                            refresh_result = resource_service.refresh_resource(
                                avid,
                                scrape=refresh_metadata,
                                download_cover=refresh_metadata,
                            )

                            refresh_info["metadata_refreshed"] = refresh_metadata
                            refresh_info["m3u8_refreshed"] = refresh_m3u8
                            refresh_info["cover_saved"] = refresh_result["cover_saved"]
                            refresh_info["metadata_saved"] = refresh_result[
                                "metadata_saved"
                            ]
                            refresh_info["scraped"] = refresh_result.get(
                                "scraped", False
                            )

                        except ResourceNotFoundError as e:
                            results.append(
                                {
                                    "action": "refresh",
                                    "avid": avid,
                                    "code": 404,
                                    "message": str(e),
                                    "resource": None,
                                }
                            )
                            continue

                        except Exception as e:
                            logger.error(f"批量刷新资源失败: {avid}, 错误: {e}", exc_info=True)
                            results.append(
                                {
                                    "action": "refresh",
                                    "avid": avid,
                                    "code": 500,
                                    "message": f"刷新失败: {str(e)}",
                                    "resource": None,
                                }
                            )
                            continue

                    # 重新翻译（在元数据刷新之后）
                    if retranslate:
                        try:
                            resource.refresh_from_db()
                            from nassav.tasks import translate_title_task

                            resource.translation_status = "pending"
                            resource.translated_title = None
                            resource.save(
                                update_fields=["translation_status", "translated_title"]
                            )
                            translate_title_task.delay(avid)
                            refresh_info["translation_queued"] = True
                        except Exception as e:
                            logger.error(f"提交翻译任务失败: {e}")
                            refresh_info["translation_error"] = str(e)

                    resource.refresh_from_db()
                    resource_data = (
                        _serialize_resource_obj(resource) if resource else None
                    )
                    result_item = {
                        "action": "refresh",
                        "avid": avid,
                        "code": 200,
                        "message": "refreshed",
                        "resource": resource_data,
                    }
                    result_item.update(refresh_info)
                    results.append(result_item)

                else:
                    results.append(
                        {
                            "action": action,
                            "avid": avid,
                            "code": 400,
                            "message": "未知 action",
                            "resource": None,
                        }
                    )

            except Exception as e:
                logger.exception(f"批量操作失败: {e}")
                results.append(
                    {
                        "action": action,
                        "avid": avid,
                        "code": 500,
                        "message": str(e),
                        "resource": None,
                    }
                )

        return build_response(200, "success", {"results": results})


class DownloadsBatchSubmitView(APIView):
    """POST /api/downloads/batch_submit

    Body example: { "avids": ["ABC-123","DEF-222"] }
    """

    def post(self, request):
        data = request.data or {}
        avids = data.get("avids") or []
        results = []

        from .tasks import submit_download_task

        for a in avids:
            avid = str(a).upper()
            try:
                task_result, is_duplicate = submit_download_task(avid)
                if is_duplicate:
                    results.append(
                        {
                            "avid": avid,
                            "code": 409,
                            "message": "下载任务已存在",
                            "task_id": None,
                        }
                    )
                else:
                    results.append(
                        {
                            "avid": avid,
                            "code": 202,
                            "message": "submitted",
                            "task_id": task_result.id,
                        }
                    )
            except Exception as e:
                logger.exception(f"批量提交下载失败: {e}")
                results.append(
                    {"avid": avid, "code": 500, "message": str(e), "task_id": None}
                )

        return build_response(200, "success", {"results": results})


class ResourceStatusView(APIView):
    """
    PATCH /api/resource/{avid}/status
    更新资源的观看状态和收藏状态

    请求参数:
        watched: 是否已观看 (boolean, optional)
        is_favorite: 是否收藏 (boolean, optional)
    """

    def patch(self, request, avid):
        avid = avid.upper()

        try:
            from nassav.models import AVResource

            resource = AVResource.objects.filter(avid=avid).first()
            if not resource:
                return build_response(404, f"资源 {avid} 不存在", None)

            data = request.data or {}
            updated_fields = []

            # 更新 watched 字段
            if "watched" in data:
                watched = data.get("watched")
                if not isinstance(watched, bool):
                    return build_response(400, "watched 参数必须是布尔值", None)
                resource.watched = watched
                updated_fields.append("watched")

            # 更新 is_favorite 字段
            if "is_favorite" in data:
                is_favorite = data.get("is_favorite")
                if not isinstance(is_favorite, bool):
                    return build_response(400, "is_favorite 参数必须是布尔值", None)
                resource.is_favorite = is_favorite
                updated_fields.append("is_favorite")

            if not updated_fields:
                return build_response(400, "未提供任何要更新的字段", None)

            resource.save(update_fields=updated_fields)

            return build_response(
                200,
                "success",
                {
                    "avid": avid,
                    "watched": resource.watched,
                    "is_favorite": resource.is_favorite,
                },
            )
        except Exception as e:
            logger.error(f"更新资源状态失败: {e}")
            return build_response(500, f"更新失败: {str(e)}", None)


class MockDownloadView(APIView):
    """
    POST /api/downloads/mock/{avid}
    模拟下载任务接口（仅在 DEBUG 模式下可用）

    用于测试下载流程，不实际下载视频，只模拟下载过程和进度更新
    """

    def post(self, request, avid):
        """
        POST /api/downloads/mock/{avid}

        Body (可选):
        {
            "duration": 30  // 模拟下载持续时间（秒），默认 30
        }
        """
        # 检查是否在 DEBUG 模式
        if not settings.DEBUG:
            return build_response(403, "此接口仅在 DEBUG 模式下可用", None)

        avid = avid.upper()
        data = request.data or {}
        duration = int(data.get("duration", 30))

        # 验证 duration 范围
        if duration < 1 or duration > 300:
            return build_response(400, "持续时间必须在 1-300 秒之间", None)

        # 检查资源是否存在于数据库
        try:
            from nassav.models import AVResource

            resource = AVResource.objects.filter(avid=avid).first()
            if not resource:
                return build_response(404, f"{avid} 的元数据不存在", None)
        except Exception as e:
            logger.error(f"查询资源失败: {e}")
            return Response(
                {"code": 500, "message": "服务器内部错误", "data": None},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # 提交模拟下载任务
        from .tasks import submit_mock_download_task

        try:
            task_result, is_duplicate = submit_mock_download_task(avid, duration)

            if is_duplicate:
                return build_response(409, "下载任务已存在", None)

            return build_response(
                202,
                "模拟下载任务已提交",
                {
                    "avid": avid,
                    "task_id": task_result.id,
                    "status": "pending",
                    "duration": duration,
                    "mock": True,
                },
            )
        except Exception as e:
            logger.error(f"提交模拟下载任务失败: {e}")
            return build_response(500, f"提交失败: {str(e)}", None)
