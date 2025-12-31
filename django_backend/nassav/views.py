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

        data = {
            'metadata': serializer.data,
            'total_pages': pagination.get('pages', 1),
            'total_num': pagination.get('total', 0),
        }

        return build_response(200, 'success', data)


class ResourceCoverView(APIView):
    """
    GET /api/resource/cover?avid=
    根据avid获取封面图片
    """

    def get(self, request):
        avid = request.query_params.get('avid', '').upper()
        if not avid:
            return build_response(400, 'avid参数缺失', None)

        # 查找封面文件 - 新布局: COVER_DIR/{avid}.{ext}
        from pathlib import Path
        import mimetypes

        cover_path = Path(settings.COVER_DIR) / f"{avid}.jpg"
        if not cover_path.exists():
            for ext in ['.png', '.jpeg', '.webp', '.jpg']:
                alt_path = Path(settings.COVER_DIR) / f"{avid}{ext}"
                if alt_path.exists():
                    cover_path = alt_path
                    break

        if not cover_path.exists():
            return Response({
                'code': 404,
                'message': f'封面 {avid} 不存在',
                'data': None
            }, status=status.HTTP_404_NOT_FOUND)

        # 使用 as_attachment=False 确保正确的流式处理，自动设置 content_type
        ctype, _ = mimetypes.guess_type(str(cover_path))
        if not ctype:
            ctype = 'application/octet-stream'
        return FileResponse(open(cover_path, 'rb'), content_type=ctype, as_attachment=False)


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

            return build_response(200, 'success', metadata)
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

        return build_response(201, 'success', {
            'avid': info.avid,
            'title': info.title,
            'source': info.source,
            'cover_downloaded': save_result['cover_saved'],
            'html_saved': save_result['html_saved'],
            'metadata_saved': save_result['metadata_saved'],
            'scraped': save_result.get('scraped', False)
        })


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

        return Response({
            'code': 200,
            'message': 'success',
            'data': {
                'avid': info.avid,
                'title': info.title,
                'source': info.source,
                'cover_downloaded': save_result['cover_saved'],
                'html_saved': save_result['html_saved'],
                'metadata_saved': save_result['metadata_saved'],
                'scraped': save_result.get('scraped', False)
            }
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

            # 同步删除数据库中的记录（若存在）
            try:
                from nassav.models import AVResource
                AVResource.objects.filter(avid=avid).delete()
            except Exception as e:
                logger.warning(f"删除数据库记录失败: {e}")

            logger.info(f"已删除资源: {avid}")
            return build_response(200, 'success', {
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
