"""
API视图：实现6个接口
所有信息以 resource 目录中的实际资源为准
"""
import json

from django.conf import settings
from django.http import FileResponse, Http404
from loguru import logger
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import (
    NewResourceSerializer,
    DownloadRequestSerializer
)
from .services import downloader_manager


class ResourceListView(APIView):
    """
    GET /api/resource/list
    获取所有已保存资源的(avid, title)
    从 resource 目录读取元数据
    """

    def get(self, request):
        resource_dir = settings.RESOURCE_DIR
        resources = []

        if resource_dir.exists():
            for item in resource_dir.iterdir():
                if item.is_dir():
                    avid = item.name
                    metadata_path = item / f"{avid}.json"
                    if metadata_path.exists():
                        try:
                            with open(metadata_path, 'r', encoding='utf-8') as f:
                                metadata = json.load(f)
                            resources.append({
                                'avid': avid,
                                'title': metadata.get('title', ''),
                                'source': metadata.get('source', ''),
                                'release_date': metadata.get('release_date', ''),
                                'has_video': (item / f"{avid}.mp4").exists()
                            })
                        except Exception as e:
                            logger.error(f"读取 {avid} 元数据失败: {e}")

        # 按 avid 排序
        resources.sort(key=lambda x: x['avid'], reverse=True)

        return Response({
            'code': 200,
            'message': 'success',
            'data': resources
        })


class ResourceCoverView(APIView):
    """
    GET /api/resource/cover?avid=
    根据avid获取封面图片
    """

    def get(self, request):
        avid = request.query_params.get('avid', '').upper()
        if not avid:
            return Response({
                'code': 400,
                'message': 'avid参数缺失'
            }, status=status.HTTP_400_BAD_REQUEST)

        # 查找封面文件 - 路径: resource/{avid}/{avid}.jpg
        resource_dir = settings.RESOURCE_DIR / avid
        cover_path = resource_dir / f"{avid}.jpg"
        if not cover_path.exists():
            # 尝试其他格式
            for ext in ['.png', '.jpeg', '.webp']:
                alt_path = resource_dir / f"{avid}{ext}"
                if alt_path.exists():
                    cover_path = alt_path
                    break

        if not cover_path.exists():
            raise Http404(f"封面 {avid} 不存在")

        return FileResponse(
            open(cover_path, 'rb'),
            content_type='image/jpeg'
        )


class DownloadsListView(APIView):
    """
    GET /api/resource/downloads/list
    获取已下载的所有视频的avid
    """

    def get(self, request):
        resource_dir = settings.RESOURCE_DIR
        downloaded_avids = []

        if resource_dir.exists():
            for item in resource_dir.iterdir():
                if item.is_dir():
                    # 检查是否存在mp4文件
                    mp4_file = item / f"{item.name}.mp4"
                    if mp4_file.exists():
                        downloaded_avids.append(item.name)

        return Response({
            'code': 200,
            'message': 'success',
            'data': downloaded_avids
        })


class DownloadsMetadataView(APIView):
    """
    GET /api/resource/downloads/metadata?avid=
    根据avid获取视频元数据
    """

    def get(self, request):
        avid = request.query_params.get('avid', '').upper()
        if not avid:
            return Response({
                'code': 400,
                'message': 'avid参数缺失'
            }, status=status.HTTP_400_BAD_REQUEST)

        # 查找元数据文件 - 路径: resource/{avid}/{avid}.json
        resource_dir = settings.RESOURCE_DIR / avid
        metadata_path = resource_dir / f"{avid}.json"
        if not metadata_path.exists():
            return Response({
                'code': 404,
                'message': f'资源 {avid} 的元数据不存在'
            }, status=status.HTTP_404_NOT_FOUND)

        try:
            with open(metadata_path, 'r', encoding='utf-8') as f:
                metadata = json.load(f)

            # 添加额外信息
            mp4_path = resource_dir / f"{avid}.mp4"
            if mp4_path.exists():
                metadata['file_size'] = mp4_path.stat().st_size
                metadata['file_exists'] = True
            else:
                metadata['file_exists'] = False

            return Response({
                'code': 200,
                'message': 'success',
                'data': metadata
            })
        except Exception as e:
            logger.error(f"读取元数据失败: {e}")
            return Response({
                'code': 500,
                'message': f'读取元数据失败: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class NewResourceView(APIView):
    """
    POST /api/resource/new
    通过avid获取资源信息并保存（HTML、封面、元数据）
    若遍历所有的源都无法获取，则返回错误信息
    """

    def post(self, request):
        serializer = NewResourceSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                'code': 400,
                'message': '参数错误',
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        avid = serializer.validated_data['avid'].upper()

        # 检查资源是否已存在（基于 resource 目录）
        resource_dir = settings.RESOURCE_DIR / avid
        metadata_path = resource_dir / f"{avid}.json"
        if metadata_path.exists():
            try:
                with open(metadata_path, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                return Response({
                    'code': 409,
                    'message': '资源已存在',
                    'data': {
                        'avid': avid,
                        'title': metadata.get('title', ''),
                        'source': metadata.get('source', '')
                    }
                })
            except Exception:
                pass  # 元数据损坏，重新获取

        # 遍历所有源获取信息
        result = downloader_manager.get_info_from_any_source(avid)
        if not result:
            return Response({
                'code': 404,
                'message': f'无法从任何源获取 {avid} 的信息'
            }, status=status.HTTP_404_NOT_FOUND)

        info, downloader, html = result

        # 一次性保存所有资源（HTML、封面、元数据）到 resource/{avid}/
        save_result = downloader_manager.save_all_resources(avid, info, downloader, html)
        if not save_result['cover_saved']:
            logger.warning(f"封面下载失败: {avid}")

        return Response({
            'code': 201,
            'message': 'success',
            'data': {
                'avid': info.avid,
                'title': info.title,
                'source': info.source,
                'cover_downloaded': save_result['cover_saved'],
                'html_saved': save_result['html_saved'],
                'metadata_saved': save_result['metadata_saved'],
                'scrapped': save_result.get('scrapped', False)
            }
        }, status=status.HTTP_201_CREATED)


class NewDownloadView(APIView):
    """
    POST /api/resource/downloads/new
    通过avid下载视频，此avid的元数据必须已存在于 resource 目录中
    """

    def post(self, request):
        serializer = DownloadRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                'code': 400,
                'message': '参数错误',
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        avid = serializer.validated_data['avid'].upper()

        # 检查元数据是否存在
        resource_dir = settings.RESOURCE_DIR / avid
        metadata_path = resource_dir / f"{avid}.json"
        if not metadata_path.exists():
            return Response({
                'code': 404,
                'message': f'{avid} 的元数据不存在，请先调用 /api/resource/new 添加资源'
            }, status=status.HTTP_404_NOT_FOUND)

        # 检查是否已下载 - 路径: resource/{avid}/{avid}.mp4
        mp4_path = resource_dir / f"{avid}.mp4"
        if mp4_path.exists():
            return Response({
                'code': 409,
                'message': '视频已下载',
                'data': {
                    'avid': avid,
                    'status': 'completed',
                    'file_size': mp4_path.stat().st_size
                }
            })

        # 使用Celery异步下载
        from .tasks import download_video_task
        task = download_video_task.delay(avid)

        return Response({
            'code': 202,
            'message': '下载任务已提交',
            'data': {
                'avid': avid,
                'task_id': task.id,
                'status': 'pending'
            }
        }, status=status.HTTP_202_ACCEPTED)
