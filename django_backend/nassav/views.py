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
from .services import source_manager


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
    设置指定源的 Cookie
    """

    def post(self, request):
        serializer = SourceCookieSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                'code': 400,
                'message': '参数错误',
                'data': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        source_name = serializer.validated_data['source']
        cookie = serializer.validated_data['cookie']

        # 检查源是否存在
        available_sources = [s.lower() for s in source_manager.sources.keys()]
        if source_name.lower() not in available_sources:
            return Response({
                'code': 404,
                'message': f'源 {source_name} 不存在',
                'data': {
                    'available_sources': list(source_manager.sources.keys())
                }
            }, status=status.HTTP_404_NOT_FOUND)

        # 如果 cookie 为 "auto"，自动获取
        if cookie.lower() == "auto":
            try:
                # 获取源实例（不区分大小写）
                source_instance = None
                for name, source in source_manager.sources.items():
                    if name.lower() == source_name.lower():
                        source_instance = source
                        break

                if not source_instance:
                    return Response({
                        'code': 500,
                        'message': f'无法获取 {source_name} 实例',
                        'data': None
                    }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

                # 自动获取cookie
                success = source_instance.set_cookie_auto(force_refresh=True)
                if success:
                    return Response({
                        'code': 200,
                        'message': 'Cookie自动获取成功',
                        'data': {
                            'source': source_name,
                            'cookie_set': True
                        }
                    })
                else:
                    return Response({
                        'code': 500,
                        'message': 'Cookie自动获取失败',
                        'data': None
                    }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            except Exception as e:
                logger.error(f"自动获取Cookie失败: {e}")
                return Response({
                    'code': 500,
                    'message': f'自动获取Cookie失败: {str(e)}',
                    'data': None
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # 手动设置 cookie
        success = source_manager.set_source_cookie(source_name, cookie)
        if success:
            return Response({
                'code': 200,
                'message': 'success',
                'data': {
                    'source': source_name,
                    'cookie_set': True,
                    'auto_fetched': False
                }
            })
        else:
            return Response({
                'code': 500,
                'message': '设置 Cookie 失败',
                'data': None
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


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
                'message': 'avid参数缺失',
                'data': None
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
            return Response({
                'code': 404,
                'message': f'封面 {avid} 不存在',
                'data': None
            }, status=status.HTTP_404_NOT_FOUND)

        # 使用 as_attachment=False 确保正确的流式处理
        return FileResponse(
            open(cover_path, 'rb'),
            content_type='image/jpeg',
            as_attachment=False
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

        resource_dir = settings.RESOURCE_DIR / avid
        mp4_path = resource_dir / f"{avid}.mp4"

        if not mp4_path.exists():
            return Response({
                'code': 404,
                'message': f'视频 {avid} 不存在',
                'data': None
            }, status=status.HTTP_404_NOT_FOUND)

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

        return Response({
            'code': 200,
            'message': 'success',
            'data': {
                "abspath": prefixed
            }
        })


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

        # 查找元数据文件 - 路径: resource/{avid}/{avid}.json
        resource_dir = settings.RESOURCE_DIR / avid
        metadata_path = resource_dir / f"{avid}.json"
        if not metadata_path.exists():
            return Response({
                'code': 404,
                'message': f'资源 {avid} 的元数据不存在',
                'data': None
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
                'message': f'读取元数据失败: {str(e)}',
                'data': None
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


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
            return Response({
                'code': 400,
                'message': '参数错误',
                'data': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        avid = serializer.validated_data['avid'].upper()
        source = serializer.validated_data.get('source', 'any').lower()

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
                        'source': metadata.get('source', ''),
                        'cover_downloaded': True,
                        'html_saved': True,
                        'metadata_saved': True,
                        'scraped': bool(metadata.get('release_date'))
                    }
                })
            except Exception:
                pass  # 元数据损坏，重新获取

        # 根据 downloader 参数选择获取方式
        if source == 'any':
            result = source_manager.get_info_from_any_source(avid)
            error_msg = f'无法从任何源获取 {avid} 的信息'
        else:
            # 检查指定源是否存在
            available_sources = [s.lower() for s in source_manager.sources.keys()]
            if source not in available_sources:
                return Response({
                    'code': 400,
                    'message': f'源 {source} 不存在',
                    'data': {
                        'available_sources': list(source_manager.sources.keys())
                    }
                }, status=status.HTTP_400_BAD_REQUEST)
            result = source_manager.get_info_from_source(avid, source)
            error_msg = f'从 {source} 获取 {avid} 失败'

        if not result:
            return Response({
                'code': 404,
                'message': error_msg,
                'data': None
            }, status=status.HTTP_404_NOT_FOUND)

        info, source, html = result

        # 一次性保存所有资源（HTML、封面、元数据）到 resource/{avid}/
        save_result = source_manager.save_all_resources(avid, info, source, html)
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
                'scraped': save_result.get('scraped', False)
            }
        }, status=status.HTTP_201_CREATED)


class DownloadView(APIView):
    def post(self, request, avid):
        """
        POST /api/resource/downloads
        通过avid下载视频，此avid的元数据必须已存在于 resource 目录中
        """
        avid = avid.upper()

        # 检查元数据是否存在
        resource_dir = settings.RESOURCE_DIR / avid
        metadata_path = resource_dir / f"{avid}.json"
        if not metadata_path.exists():
            return Response({
                'code': 404,
                'message': f'{avid} 的元数据不存在，请先调用 /api/resource/new 添加资源',
                'data': None
            }, status=status.HTTP_404_NOT_FOUND)

        # 检查是否已下载 - 路径: resource/{avid}/{avid}.mp4
        mp4_path = resource_dir / f"{avid}.mp4"
        if mp4_path.exists():
            return Response({
                'code': 409,
                'message': '视频已下载',
                'data': {
                    'avid': avid,
                    'task_id': None,
                    'status': 'completed',
                    'file_size': mp4_path.stat().st_size
                }
            })

        # 使用Celery异步下载（带去重检查）
        from .tasks import submit_download_task
        task_result, is_duplicate = submit_download_task(avid)

        if is_duplicate:
            return Response({
                'code': 409,
                'message': '下载任务已存在',
                'data': None
            })

        task = task_result

        return Response({
            'code': 202,
            'message': '下载任务已提交',
            'data': {
                'avid': avid,
                'task_id': task.id,
                'status': 'pending',
                'file_size': None
            }
        }, status=status.HTTP_202_ACCEPTED)

    def delete(self, request, avid):
        """
        DELETE /api/downloads/{avid}
        删除已下载的视频文件
        """
        avid = avid.upper()
        resource_dir = settings.RESOURCE_DIR / avid
        mp4_path = resource_dir / f"{avid}.mp4"

        if not mp4_path.exists():
            return Response({
                'code': 404,
                'message': f'视频 {avid} 不存在',
                'data': None
            }, status=status.HTTP_404_NOT_FOUND)

        try:
            file_size = mp4_path.stat().st_size
            mp4_path.unlink()
            logger.info(f"已删除视频: {avid}")
            return Response({
                'code': 200,
                'message': 'success',
                'data': {
                    'avid': avid,
                    'deleted_file': f"{avid}.mp4",
                    'file_size': file_size
                }
            })
        except Exception as e:
            logger.error(f"删除视频失败: {e}")
            return Response({
                'code': 500,
                'message': f'删除失败: {str(e)}',
                'data': None
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class RefreshResourceView(APIView):
    """
    POST /api/resource/refresh/{avid}
    刷新已有资源的元数据和m3u8链接，使用原有source获取
    """

    def post(self, request, avid):
        avid = avid.upper()

        # 检查资源是否存在
        resource_dir = settings.RESOURCE_DIR / avid
        metadata_path = resource_dir / f"{avid}.json"
        if not metadata_path.exists():
            return Response({
                'code': 404,
                'message': f'{avid} 的资源不存在，请先调用 /api/resource/new 添加资源',
                'data': None
            }, status=status.HTTP_404_NOT_FOUND)

        # 读取现有元数据获取 source
        try:
            with open(metadata_path, 'r', encoding='utf-8') as f:
                old_metadata = json.load(f)
            source = old_metadata.get('source', '')
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
        resource_dir = settings.RESOURCE_DIR / avid

        if not resource_dir.exists():
            return Response({
                'code': 404,
                'message': f'资源 {avid} 不存在',
                'data': None
            }, status=status.HTTP_404_NOT_FOUND)

        try:
            # 收集删除的文件信息
            deleted_files = []
            for f in resource_dir.iterdir():
                deleted_files.append(f.name)

            shutil.rmtree(resource_dir)
            logger.info(f"已删除资源目录: {avid}")
            return Response({
                'code': 200,
                'message': 'success',
                'data': {
                    'avid': avid,
                    'deleted_files': deleted_files
                }
            })
        except Exception as e:
            logger.error(f"删除资源目录失败: {e}")
            return Response({
                'code': 500,
                'message': f'删除失败: {str(e)}',
                'data': None
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
