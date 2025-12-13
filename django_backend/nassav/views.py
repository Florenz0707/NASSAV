"""
API视图：实现6个接口
"""
import json
import os
from pathlib import Path
from django.conf import settings
from django.http import FileResponse, Http404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from loguru import logger

from .models import AVInfo
from .serializers import (
    AVInfoListSerializer,
    NewResourceSerializer,
    DownloadRequestSerializer
)
from .services import downloader_manager, video_download_service


class ResourceListView(APIView):
    """
    GET /api/resource/list
    获取数据库中的所有(avid, title)
    """

    def get(self, request):
        queryset = AVInfo.objects.all()
        serializer = AVInfoListSerializer(queryset, many=True)
        return Response({
            'code': 0,
            'message': 'success',
            'data': serializer.data
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

        # 查找封面文件
        cover_path = settings.COVER_DIR / f"{avid}.jpg"
        if not cover_path.exists():
            # 尝试其他格式
            for ext in ['.png', '.jpeg', '.webp']:
                alt_path = settings.COVER_DIR / f"{avid}{ext}"
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
        video_dir = settings.VIDEO_DIR
        downloaded_avids = []

        if video_dir.exists():
            for item in video_dir.iterdir():
                if item.is_dir():
                    # 检查是否存在mp4文件
                    mp4_file = item / f"{item.name}.mp4"
                    if mp4_file.exists():
                        downloaded_avids.append(item.name)

        return Response({
            'code': 0,
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

        # 查找元数据文件
        metadata_path = settings.VIDEO_DIR / avid / f"{avid}.json"
        if not metadata_path.exists():
            return Response({
                'code': 404,
                'message': f'视频 {avid} 的元数据不存在'
            }, status=status.HTTP_404_NOT_FOUND)

        try:
            with open(metadata_path, 'r', encoding='utf-8') as f:
                metadata = json.load(f)

            # 添加额外信息
            mp4_path = settings.VIDEO_DIR / avid / f"{avid}.mp4"
            if mp4_path.exists():
                metadata['file_size'] = mp4_path.stat().st_size
                metadata['file_exists'] = True
            else:
                metadata['file_exists'] = False

            return Response({
                'code': 0,
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
    通过avid获取title并下载cover
    若遍历所有的源都无法获取，则删去该数据条目并返回错误信息
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

        # 检查是否已存在
        if AVInfo.objects.filter(avid=avid).exists():
            av_info = AVInfo.objects.get(avid=avid)
            return Response({
                'code': 0,
                'message': '资源已存在',
                'data': {
                    'avid': av_info.avid,
                    'title': av_info.title,
                    'source': av_info.source
                }
            })

        # 遍历所有源获取信息
        result = downloader_manager.get_info_from_any_source(avid)
        if not result:
            return Response({
                'code': 404,
                'message': f'无法从任何源获取 {avid} 的信息'
            }, status=status.HTTP_404_NOT_FOUND)

        info, downloader = result

        # 下载封面
        cover_path = downloader_manager.download_cover(avid, downloader)
        if not cover_path:
            logger.warning(f"封面下载失败: {avid}")

        # 保存到数据库
        av_info = AVInfo.objects.create(
            avid=avid,
            title=info.title,
            source=info.source
        )

        return Response({
            'code': 0,
            'message': 'success',
            'data': {
                'avid': av_info.avid,
                'title': av_info.title,
                'source': av_info.source,
                'cover_downloaded': cover_path is not None
            }
        }, status=status.HTTP_201_CREATED)


class NewDownloadView(APIView):
    """
    POST /api/resource/downloads/new
    通过avid下载视频，此avid必须已经验证可获取，即存在于数据库中
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

        # 检查是否存在于数据库中
        if not AVInfo.objects.filter(avid=avid).exists():
            return Response({
                'code': 404,
                'message': f'{avid} 不存在于数据库中，请先调用 /api/resource/new 添加资源'
            }, status=status.HTTP_404_NOT_FOUND)

        # 检查是否已下载
        mp4_path = settings.VIDEO_DIR / avid / f"{avid}.mp4"
        if mp4_path.exists():
            return Response({
                'code': 0,
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
            'code': 0,
            'message': '下载任务已提交',
            'data': {
                'avid': avid,
                'task_id': task.id,
                'status': 'pending'
            }
        }, status=status.HTTP_202_ACCEPTED)
