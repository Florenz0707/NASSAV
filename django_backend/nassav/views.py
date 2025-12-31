"""
API视图：实现资源管理接口
所有信息以 resource 目录中的实际资源为准
统一响应格式: {"code": xxx, "message": xxx, "data": data}
"""
import json

from django.conf import settings
from django.http import FileResponse
from loguru import logger
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import (
    NewResourceSerializer,
    SourceCookieSerializer
)
from .services import source_manager, list_resources
from .api_utils import build_response
from .utils import generate_thumbnail
from .utils import generate_etag_for_file, parse_http_if_modified_since
from django.urls import reverse
from django.utils.http import http_date


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
        'avid': resource.avid,
        'title': resource.title or '',
        'm3u8': resource.m3u8 or '',
        'source': resource.source or '',
        'release_date': resource.release_date or '',
        'duration': resource.duration,
        'actors': actors,
        'genres': genres,
        'file_size': resource.file_size,
        'file_exists': bool(resource.file_exists),
    }


class SourceListView(APIView):
    """
    GET /api/source/list
    获取所有可用的下载源名称列表
    """

    def get(self, request):
        sources = list(source_manager.sources.keys())
        return Response({
            'code': 200,
            'message': 'success',
            'data': sources
        })


class SourceCookieView(APIView):
    """
    POST /api/source/cookie
    设置或自动获取指定源的 Cookie。

    Request JSON:
      - source: 源名称 (required)
      - cookie: 手动设置的 cookie (optional)
      - auto: 是否自动获取 cookie (boolean, optional)
    """

    def post(self, request):
        data = request.data or {}
        source_name = data.get('source')
        cookie = data.get('cookie')
        auto = bool(data.get('auto', False))

        if not source_name:
            return Response({'code': 400, 'message': 'source 参数缺失', 'data': None},
                            status=status.HTTP_400_BAD_REQUEST)

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
                    return Response({'code': 404, 'message': f'无法获取 {source_name} 实例', 'data': None},
                                    status=status.HTTP_404_NOT_FOUND)

                success = False
                try:
                    success = source_instance.set_cookie_auto(force_refresh=True)
                except Exception as e:
                    logger.error(f"自动获取 Cookie 失败: {e}")

                if success:
                    return Response({'code': 200, 'message': 'Cookie 自动获取成功',
                                     'data': {'source': source_name, 'cookie_set': True}})
                else:
                    return Response({'code': 500, 'message': 'Cookie 自动获取失败', 'data': None},
                                    status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            except Exception as e:
                logger.error(f"自动获取 Cookie 异常: {e}")
                return Response({'code': 500, 'message': f'自动获取 Cookie 异常: {str(e)}', 'data': None},
                                status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # 否则如果提供了 cookie 则手动设置并保存到 DB
        if cookie:
            success = source_manager.set_source_cookie(source_name, cookie)
            if success:
                return Response({'code': 200, 'message': 'success',
                                 'data': {'source': source_name, 'cookie_set': True, 'auto_fetched': False}})
            else:
                return Response({'code': 500, 'message': '设置 Cookie 失败', 'data': None},
                                status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({'code': 400, 'message': '未提供 cookie 且 auto 未设置为 True', 'data': None},
                        status=status.HTTP_400_BAD_REQUEST)


class ResourceListView(APIView):
    """
    GET /api/resource/list
    获取所有已保存资源的(avid, title)
    支持排序和分页
    参数:
        sort_by: 排序字段（avid, metadata_create_time, video_create_time, source）
        order: 排序方式（asc, desc）
        page: 页码（默认1）
        page_size: 每页数量（默认20）
    从 resource 目录读取元数据
    """

    def get(self, request):
        # 使用数据库查询 AVResource，提高性能并支持排序/分页
        from nassav.models import AVResource

        # 获取排序和分页参数
        sort_by = request.query_params.get('sort_by', 'avid')
        order = request.query_params.get('order', 'desc')
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 20))

        sort_map = {
            'avid': 'avid',
            'metadata_create_time': 'metadata_saved_at',
            'video_create_time': 'video_saved_at',
            'source': 'source'
        }
        sort_field = sort_map.get(sort_by, 'avid')
        if order == 'desc':
            sort_field = f'-{sort_field}'

        qs = AVResource.objects.all().order_by(sort_field)
        total = qs.count()
        start = (page - 1) * page_size
        paged = qs[start:start + page_size]

        data = []
        for r in paged:
            data.append({
                'avid': r.avid,
                'title': r.title or '',
                'source': r.source or '',
                'release_date': r.release_date or '',
                'has_video': bool(r.file_exists),
                'metadata_create_time': r.metadata_saved_at.timestamp() if r.metadata_saved_at else None,
                'video_create_time': r.video_saved_at.timestamp() if r.video_saved_at else None,
            })

        return build_response(200, 'success', data)


class ResourcesListView(APIView):
    """GET /api/resources/ - consolidated resource listing with filters/pagination"""

    def get(self, request):
        # support legacy sort_by / order params from older endpoints
        params = request.query_params.copy()
        sort_by = params.get('sort_by')
        order = params.get('order', 'desc')
        if sort_by:
            sort_map = {
                'avid': 'avid',
                'metadata_create_time': 'metadata_saved_at',
                'video_create_time': 'video_saved_at',
                'source': 'source'
            }
            sort_field = sort_map.get(sort_by, None)
            if sort_field:
                if order == 'desc':
                    params['ordering'] = f'-{sort_field}'
                else:
                    params['ordering'] = sort_field

        objs, pagination = list_resources(params)
        # reuse ResourceSummarySerializer
        from .serializers import ResourceSummarySerializer
        serializer = ResourceSummarySerializer(objs, many=True)

        # return standardized envelope with pagination field
        return build_response(200, 'success', serializer.data, pagination=pagination)


class ResourceCoverView(APIView):
    """
    GET /api/resource/cover?avid=
    根据avid获取封面图片
    """

    def get(self, request):
        avid = request.query_params.get('avid', '').upper()
        if not avid:
            return build_response(400, 'avid参数缺失', None)
        # 支持 size 参数：small|medium|large（保存到 COVER_DIR/thumbnails/{size}/{avid}.jpg）
        from pathlib import Path
        import mimetypes

        size = request.query_params.get('size')

        cover_dir = Path(settings.COVER_DIR)
        # find original cover (any extension)
        cover_path = None
        for ext in ['.jpg', '.jpeg', '.png', '.webp']:
            p = cover_dir / f"{avid}{ext}"
            if p.exists():
                cover_path = p
                break

        if not cover_path:
            return Response({
                'code': 404,
                'message': f'封面 {avid} 不存在',
                'data': None
            }, status=status.HTTP_404_NOT_FOUND)

        # if no size requested, return original file (with conditional handling)
        if not size:
            ctype, _ = mimetypes.guess_type(str(cover_path))
            if not ctype:
                ctype = 'application/octet-stream'
            # ETag + Last-Modified
            try:
                etag = generate_etag_for_file(cover_path)
            except Exception:
                etag = '"0"'

            ims = request.headers.get('If-Modified-Since') or request.META.get('HTTP_IF_MODIFIED_SINCE')
            inm = request.headers.get('If-None-Match') or request.META.get('HTTP_IF_NONE_MATCH')
            # check ETag
            if inm and etag and inm.strip() == etag:
                resp = Response(status=status.HTTP_304_NOT_MODIFIED)
                resp['ETag'] = etag
                resp['Last-Modified'] = http_date(cover_path.stat().st_mtime)
                return resp
            # check If-Modified-Since
            ims_ts = parse_http_if_modified_since(ims)
            if ims_ts is not None and int(cover_path.stat().st_mtime) <= ims_ts:
                resp = Response(status=status.HTTP_304_NOT_MODIFIED)
                resp['ETag'] = etag
                resp['Last-Modified'] = http_date(cover_path.stat().st_mtime)
                return resp

            resp = FileResponse(open(cover_path, 'rb'), content_type=ctype, as_attachment=False)
            # Cache long
            resp['Cache-Control'] = 'public, max-age=31536000'
            resp['ETag'] = etag
            resp['Last-Modified'] = http_date(cover_path.stat().st_mtime)
            return resp

        size = str(size).lower()
        sizes_map = {'small': 200, 'medium': 600, 'large': 1200}
        if size not in sizes_map:
            return build_response(400, 'size 参数无效，支持 small|medium|large', None)

        thumb_dir = Path(getattr(settings, 'THUMBNAIL_DIR', settings.COVER_DIR / 'thumbnails'))
        thumb_path = thumb_dir / size / f"{avid}.jpg"

        # if thumbnail exists and up-to-date, serve it
        try:
            if thumb_path.exists() and thumb_path.stat().st_mtime >= cover_path.stat().st_mtime:
                # Conditional checks
                etag = generate_etag_for_file(thumb_path)
                inm = request.headers.get('If-None-Match') or request.META.get('HTTP_IF_NONE_MATCH')
                ims = request.headers.get('If-Modified-Since') or request.META.get('HTTP_IF_MODIFIED_SINCE')
                if inm and inm.strip() == etag:
                    resp = Response(status=status.HTTP_304_NOT_MODIFIED)
                    resp['ETag'] = etag
                    resp['Last-Modified'] = http_date(thumb_path.stat().st_mtime)
                    return resp
                ims_ts = parse_http_if_modified_since(ims)
                if ims_ts is not None and int(thumb_path.stat().st_mtime) <= ims_ts:
                    resp = Response(status=status.HTTP_304_NOT_MODIFIED)
                    resp['ETag'] = etag
                    resp['Last-Modified'] = http_date(thumb_path.stat().st_mtime)
                    return resp

                resp = FileResponse(open(thumb_path, 'rb'), content_type='image/jpeg', as_attachment=False)
                resp['Cache-Control'] = 'public, max-age=31536000'
                resp['ETag'] = etag
                resp['Last-Modified'] = http_date(thumb_path.stat().st_mtime)
                return resp
        except Exception:
            pass

        # try to generate thumbnail (best-effort)
        success = generate_thumbnail(cover_path, thumb_path, sizes_map[size])
        if success and thumb_path.exists():
            resp = FileResponse(open(thumb_path, 'rb'), content_type='image/jpeg', as_attachment=False)
            resp['Cache-Control'] = 'public, max-age=31536000'
            resp['Last-Modified'] = http_date(thumb_path.stat().st_mtime)
            return resp

        # fallback: return original
        ctype, _ = mimetypes.guess_type(str(cover_path))
        if not ctype:
            ctype = 'application/octet-stream'
        resp = FileResponse(open(cover_path, 'rb'), content_type=ctype, as_attachment=False)
        resp['Cache-Control'] = 'public, max-age=31536000'
        resp['Last-Modified'] = http_date(cover_path.stat().st_mtime)
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
                return build_response(404, f'资源 {avid} 不存在', None)

            metadata = resource.metadata if resource.metadata else {
                'avid': resource.avid,
                'title': resource.title,
                'source': resource.source,
                'release_date': resource.release_date,
            }
            # thumbnail url (small)
            # use file mtime as version token
            from pathlib import Path
            cover_dir = Path(settings.COVER_DIR)
            cover_path = None
            for ext in ['.jpg', '.jpeg', '.png', '.webp']:
                p = cover_dir / f"{avid}{ext}"
                if p.exists():
                    cover_path = p
                    break

            v = ''
            if cover_path and cover_path.exists():
                v = str(int(cover_path.stat().st_mtime))

            thumbnail_url = f"/nassav/api/resource/cover?avid={avid}&size=small"
            if v:
                thumbnail_url += f"&v={v}"

            return build_response(200, 'success', {'metadata': metadata, 'thumbnail_url': thumbnail_url})
        except Exception as e:
            logger.error(f"生成 preview 失败: {e}")
            return build_response(500, f'生成 preview 失败: {str(e)}', None)


class DownloadsListView(APIView):
    """
    GET /api/resource/downloads/list
    获取已下载的所有视频的avid
    """

    def get(self, request):
        from nassav.models import AVResource
        downloaded_avids = list(AVResource.objects.filter(file_exists=True).values_list('avid', flat=True))
        return build_response(200, 'success', downloaded_avids)


class DownloadAbspathView(APIView):
    """
    GET /api/downloads/abspath?avid=
    返回视频文件的绝对路径，并在前面拼接 config.UrlPrefix 作为前缀
    """

    def get(self, request):
        avid = request.query_params.get('avid', '').upper()
        if not avid:
            return Response({
                'code': 400,
                'message': 'avid参数缺失',
                'data': None
            }, status=status.HTTP_400_BAD_REQUEST)

        from pathlib import Path
        resource_dir = Path(settings.VIDEO_DIR)
        mp4_path = resource_dir / f"{avid}.mp4"

        if not mp4_path.exists():
            return build_response(404, f'视频 {avid} 不存在', None)

        try:
            abs_path = str(mp4_path.resolve())
        except Exception:
            abs_path = str(mp4_path.absolute())

        url_prefix = ''
        try:
            url_prefix = settings.CONFIG.get('UrlPrefix', '') if hasattr(settings, 'CONFIG') else ''
        except Exception:
            url_prefix = ''

        # 拼接前缀和绝对路径
        prefixed = f"{url_prefix}{abs_path}"

        return build_response(200, 'success', {"abspath": prefixed})


class ResourceMetadataView(APIView):
    """
    GET /api/resource/downloads/metadata?avid=
    根据avid获取视频元数据
    """

    def get(self, request):
        avid = request.query_params.get('avid', '').upper()
        if not avid:
            return Response({
                'code': 400,
                'message': 'avid参数缺失',
                'data': None
            }, status=status.HTTP_400_BAD_REQUEST)

        # 从数据库读取元数据
        try:
            from nassav.models import AVResource
            resource = AVResource.objects.filter(avid=avid).first()
            if not resource:
                return build_response(404, f'资源 {avid} 的元数据不存在', None)

            # 基于 DB 的 metadata 字段或各字段构建返回值
            metadata = resource.metadata if resource.metadata else {
                'avid': resource.avid,
                'title': resource.title,
                'source': resource.source,
                'release_date': resource.release_date,
                'duration': resource.duration,
                'actors': [a.name for a in resource.actors.all()],
                'genres': [g.name for g in resource.genres.all()],
                'm3u8': resource.m3u8,
            }

            # 添加文件信息
            metadata['file_exists'] = bool(resource.file_exists)
            metadata['file_size'] = resource.file_size if resource.file_size else None

            # Conditional request handling: ETag + Last-Modified
            try:
                import json
                from .utils import generate_etag_from_text
                etag = generate_etag_from_text(json.dumps(metadata, sort_keys=True))
            except Exception:
                etag = '"0"'

            ims = request.headers.get('If-Modified-Since') or request.META.get('HTTP_IF_MODIFIED_SINCE')
            inm = request.headers.get('If-None-Match') or request.META.get('HTTP_IF_NONE_MATCH')

            # ETag match
            if inm and inm.strip() == etag:
                resp = Response(status=status.HTTP_304_NOT_MODIFIED)
                resp['ETag'] = etag
                if resource.metadata_saved_at:
                    resp['Last-Modified'] = http_date(resource.metadata_saved_at.timestamp())
                return resp

            # If-Modified-Since match
            ims_ts = parse_http_if_modified_since(ims)
            if ims_ts is not None and resource.metadata_saved_at and int(resource.metadata_saved_at.timestamp()) <= ims_ts:
                resp = Response(status=status.HTTP_304_NOT_MODIFIED)
                resp['ETag'] = etag
                resp['Last-Modified'] = http_date(resource.metadata_saved_at.timestamp())
                return resp

            resp = build_response(200, 'success', metadata)
            resp['ETag'] = etag
            if resource.metadata_saved_at:
                resp['Last-Modified'] = http_date(resource.metadata_saved_at.timestamp())
            return resp
        except Exception as e:
            logger.error(f"读取元数据失败: {e}")
            return build_response(500, f'读取元数据失败: {str(e)}', None)


class ResourceView(APIView):
    """
    POST /api/resource/new
    通过avid获取资源信息并保存（HTML、封面、元数据）

    请求参数:
        avid: 视频编号
        downloader: 指定源名称，默认 "any" 表示尝试所有源
    """

    def post(self, request):
        serializer = NewResourceSerializer(data=request.data)
        if not serializer.is_valid():
            return build_response(400, '参数错误', serializer.errors)

        avid = serializer.validated_data['avid'].upper()
        source = serializer.validated_data.get('source', 'any').lower()

        # 检查资源是否已存在（基于数据库）
        try:
            from nassav.models import AVResource
            existing = AVResource.objects.filter(avid=avid).first()
            if existing:
                return build_response(409, '资源已存在', {
                    'avid': existing.avid,
                    'title': existing.title or '',
                    'source': existing.source or '',
                    'cover_downloaded': bool(existing.cover_filename),
                    'html_saved': False,
                    'metadata_saved': True,
                    'scraped': bool(existing.release_date)
                })
        except Exception:
            pass

        # 根据 downloader 参数选择获取方式
        if source == 'any':
            result = source_manager.get_info_from_any_source(avid)
            error_msg = f'无法从任何源获取 {avid} 的信息'
        else:
            # 检查指定源是否存在
            available_sources = [s.lower() for s in source_manager.sources.keys()]
            if source not in available_sources:
                return build_response(400, f'源 {source} 不存在', {
                    'available_sources': list(source_manager.sources.keys())
                })
            result = source_manager.get_info_from_source(avid, source)
            error_msg = f'从 {source} 获取 {avid} 失败'

        if not result:
            return build_response(404, error_msg, None)

        info, source, html = result

        # 一次性保存所有资源（HTML、封面、元数据）到 resource/{avid}/
        save_result = source_manager.save_all_resources(avid, info, source, html)
        if not save_result['cover_saved']:
            logger.warning(f"封面下载失败: {avid}")

        # 返回保存后的资源对象，便于前端局部刷新
        try:
            from nassav.models import AVResource
            resource_obj = AVResource.objects.filter(avid=avid).first()
            resource_data = _serialize_resource_obj(resource_obj) if resource_obj else None
        except Exception:
            resource_data = None

        return build_response(201, 'success', {
            'resource': resource_data,
            'cover_downloaded': save_result['cover_saved'],
            'html_saved': save_result['html_saved'],
            'metadata_saved': save_result['metadata_saved'],
            'scraped': save_result.get('scraped', False)
        })

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
                return build_response(404, f'{avid} 的元数据不存在，请先调用 /api/resource/new 添加资源', None)

            # 检查是否已下载
            if resource.file_exists:
                return build_response(409, '视频已下载', {
                    'avid': avid,
                    'task_id': None,
                    'status': 'completed',
                    'file_size': resource.file_size
                })
        except Exception:
            return Response({
                'code': 500,
                'message': '服务器内部错误',
                'data': None
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # 使用Celery异步下载（带去重检查）
        from .tasks import submit_download_task
        task_result, is_duplicate = submit_download_task(avid)

        if is_duplicate:
            return build_response(409, '下载任务已存在', None)

        task = task_result

        return build_response(202, '下载任务已提交', {
            'avid': avid,
            'task_id': task.id,
            'status': 'pending',
            'file_size': None
        })

    def delete(self, request, avid):
        """
        DELETE /api/downloads/{avid}
        删除已下载的视频文件
        """
        avid = avid.upper()
        from pathlib import Path
        mp4_path = Path(settings.VIDEO_DIR) / f"{avid}.mp4"

        if not mp4_path.exists():
            return build_response(404, f'视频 {avid} 不存在', None)

        try:
            file_size = mp4_path.stat().st_size
            mp4_path.unlink()
            try:
                from nassav.models import AVResource
                AVResource.objects.filter(avid=avid).update(file_exists=False, file_size=None, video_saved_at=None)
            except Exception as e:
                logger.warning(f"删除 mp4 后更新 DB 失败: {e}")
            logger.info(f"已删除视频: {avid}")
            return build_response(200, 'success', {
                'avid': avid,
                'deleted_file': f"{avid}.mp4",
                'file_size': file_size
            })
        except Exception as e:
            logger.error(f"删除视频失败: {e}")
            return build_response(500, f'删除失败: {str(e)}', None)


class RefreshResourceView(APIView):
    """
    POST /api/resource/refresh/{avid}
    刷新已有资源的元数据和m3u8链接，使用原有source获取
    """

    def post(self, request, avid):
        avid = avid.upper()

        # 检查资源是否存在（数据库），并根据 DB 中的 source 刷新
        try:
            from nassav.models import AVResource
            resource = AVResource.objects.filter(avid=avid).first()
            if not resource:
                return Response({
                    'code': 404,
                    'message': f'{avid} 的资源不存在，请先调用 /api/resource/new 添加资源',
                    'data': None
                }, status=status.HTTP_404_NOT_FOUND)
            source = resource.source or ''
        except Exception as e:
            logger.error(f"读取现有元数据失败: {e}")
            return Response({
                'code': 500,
                'message': f'读取现有元数据失败: {str(e)}',
                'data': None
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        if not source:
            return Response({
                'code': 400,
                'message': f'{avid} 的元数据中没有 source 信息，无法刷新',
                'data': None
            }, status=status.HTTP_400_BAD_REQUEST)

        # 使用原有 source获取新信息
        result = source_manager.get_info_from_source(avid, source)
        if not result:
            return Response({
                'code': 502,
                'message': f'从 {source} 刷新 {avid} 失败',
                'data': None
            }, status=status.HTTP_502_BAD_GATEWAY)

        info, downloader, html = result

        # 保存新资源（覆盖旧资源）
        save_result = source_manager.save_all_resources(avid, info, downloader, html)

        # 返回刷新后的资源对象，便于前端局部刷新
        try:
            from nassav.models import AVResource
            resource_obj = AVResource.objects.filter(avid=avid).first()
            resource_data = _serialize_resource_obj(resource_obj) if resource_obj else None
        except Exception:
            resource_data = None

        return build_response(200, 'success', {
            'resource': resource_data,
            'cover_downloaded': save_result['cover_saved'],
            'html_saved': save_result['html_saved'],
            'metadata_saved': save_result['metadata_saved'],
            'scraped': save_result.get('scraped', False)
        })


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
        backup_root = Path(getattr(settings, 'RESOURCE_BACKUP_DIR', Path(settings.BASE_DIR) / 'resource_backup'))

        cover_candidates = []
        for ext in ['.jpg', '.jpeg', '.png', '.webp']:
            p = cover_root / f"{avid}{ext}"
            if p.exists():
                cover_candidates.append(p)

        mp4_path = video_root / f"{avid}.mp4"
        backup_dir = backup_root / avid

        if not cover_candidates and not mp4_path.exists() and not backup_dir.exists():
            return build_response(404, f'资源 {avid} 不存在', None)

        try:
            deleted_files = []
            for p in cover_candidates:
                deleted_files.append(p.name)
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
            return build_response(200, 'success', {
                'resource': resource_data,
                'avid': avid,
                'deleted_files': deleted_files
            })
        except Exception as e:
            logger.error(f"删除资源失败: {e}")
            return build_response(500, f'删除失败: {str(e)}', None)


class TaskQueueStatusView(APIView):
    """
    GET /api/tasks/queue/status
    获取当前任务队列状态
    """

    def get(self, request):
        from .tasks import get_task_queue_status

        try:
            queue_status = get_task_queue_status()
            return build_response(200, 'success', queue_status)
        except Exception as e:
            logger.error(f"获取任务队列状态失败: {e}")
            return build_response(500, f'获取队列状态失败: {str(e)}', None)


class ResourcesBatchView(APIView):
    """POST /api/resources/batch

    Body example:
      { "actions": [ {"action":"add","avid":"ABC-123","source":"any"},
                      {"action":"delete","avid":"XYZ-001"},
                      {"action":"refresh","avid":"DEF-222"} ] }
    """

    def post(self, request):
        data = request.data or {}
        actions = data.get('actions') or []
        results = []

        for act in actions:
            action = (act.get('action') or '').lower()
            avid = (act.get('avid') or '').upper()
            if not avid:
                results.append({'action': action, 'avid': None, 'code': 400, 'message': 'avid 缺失', 'resource': None})
                continue

            try:
                if action == 'add':
                    # reuse source_manager.get_info_from_any_source or specific source
                    source = (act.get('source') or 'any').lower()
                    if source == 'any':
                        result = source_manager.get_info_from_any_source(avid)
                    else:
                        result = source_manager.get_info_from_source(avid, source)

                    if not result:
                        results.append({'action': 'add', 'avid': avid, 'code': 404, 'message': '获取信息失败', 'resource': None})
                        continue

                    info, src, html = result
                    save_result = source_manager.save_all_resources(avid, info, src, html)
                    # load serialized resource
                    from nassav.models import AVResource
                    resource_obj = AVResource.objects.filter(avid=avid).first()
                    resource_data = _serialize_resource_obj(resource_obj) if resource_obj else None
                    results.append({'action': 'add', 'avid': avid, 'code': 201, 'message': 'added', 'resource': resource_data})

                elif action == 'delete':
                    # perform delete similar to DeleteResourceView
                    import shutil
                    from pathlib import Path
                    cover_root = Path(settings.COVER_DIR)
                    video_root = Path(settings.VIDEO_DIR)
                    backup_root = Path(getattr(settings, 'RESOURCE_BACKUP_DIR', Path(settings.BASE_DIR) / 'resource_backup'))

                    cover_candidates = []
                    for ext in ['.jpg', '.jpeg', '.png', '.webp']:
                        p = cover_root / f"{avid}{ext}"
                        if p.exists():
                            cover_candidates.append(p)

                    mp4_path = video_root / f"{avid}.mp4"
                    backup_dir = backup_root / avid

                    if not cover_candidates and not mp4_path.exists() and not backup_dir.exists():
                        results.append({'action': 'delete', 'avid': avid, 'code': 404, 'message': '资源不存在', 'resource': None})
                        continue

                    deleted_files = []
                    for p in cover_candidates:
                        deleted_files.append(p.name)
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

                    results.append({'action': 'delete', 'avid': avid, 'code': 200, 'message': 'deleted', 'resource': resource_data, 'deleted_files': deleted_files})

                elif action == 'refresh':
                    # similar to RefreshResourceView
                    from nassav.models import AVResource
                    resource = AVResource.objects.filter(avid=avid).first()
                    if not resource:
                        results.append({'action': 'refresh', 'avid': avid, 'code': 404, 'message': '资源不存在', 'resource': None})
                        continue
                    source = resource.source or ''
                    if not source:
                        results.append({'action': 'refresh', 'avid': avid, 'code': 400, 'message': '没有 source 信息', 'resource': None})
                        continue

                    result = source_manager.get_info_from_source(avid, source)
                    if not result:
                        results.append({'action': 'refresh', 'avid': avid, 'code': 502, 'message': '刷新失败', 'resource': None})
                        continue

                    info, downloader, html = result
                    save_result = source_manager.save_all_resources(avid, info, downloader, html)
                    resource_obj = AVResource.objects.filter(avid=avid).first()
                    resource_data = _serialize_resource_obj(resource_obj) if resource_obj else None
                    results.append({'action': 'refresh', 'avid': avid, 'code': 200, 'message': 'refreshed', 'resource': resource_data})

                else:
                    results.append({'action': action, 'avid': avid, 'code': 400, 'message': '未知 action', 'resource': None})

            except Exception as e:
                logger.exception(f"批量操作失败: {e}")
                results.append({'action': action, 'avid': avid, 'code': 500, 'message': str(e), 'resource': None})

        return build_response(200, 'success', {'results': results})


class DownloadsBatchSubmitView(APIView):
    """POST /api/downloads/batch_submit

    Body example: { "avids": ["ABC-123","DEF-222"] }
    """

    def post(self, request):
        data = request.data or {}
        avids = data.get('avids') or []
        results = []

        from .tasks import submit_download_task

        for a in avids:
            avid = str(a).upper()
            try:
                task_result, is_duplicate = submit_download_task(avid)
                if is_duplicate:
                    results.append({'avid': avid, 'code': 409, 'message': '下载任务已存在', 'task_id': None})
                else:
                    results.append({'avid': avid, 'code': 202, 'message': 'submitted', 'task_id': task_result.id})
            except Exception as e:
                logger.exception(f"批量提交下载失败: {e}")
                results.append({'avid': avid, 'code': 500, 'message': str(e), 'task_id': None})

        return build_response(200, 'success', {'results': results})
