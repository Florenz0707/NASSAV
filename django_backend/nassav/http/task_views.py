"""
API视图：实现资源管理接口
所有信息以 resource 目录中的实际资源为准
统一响应格式: {"code": xxx, "message": xxx, "data": data}
"""

from django.conf import settings
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiResponse, extend_schema
from loguru import logger
from rest_framework import status
from rest_framework.response import Response

from nassav.api_utils import build_response
from nassav.http_base import SchemaAPIView
from nassav.resource_deletion import (
    InvalidResourceIdentifier,
    ResourceDeletionFailure,
    ResourceTaskConflict,
    resource_deletion_service,
)


class DownloadView(SchemaAPIView):
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
                    404,
                    f"{avid} 的元数据不存在，请先调用 /api/resource/new 添加资源",
                    None,
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
        from nassav.tasks import submit_download_task

        task_result, is_duplicate = submit_download_task(avid)

        if is_duplicate:
            return build_response(409, "下载任务已存在", None)

        assert task_result is not None, (
            "task_result should not be None when not duplicate"
        )
        task = task_result

        return build_response(
            202,
            "下载任务已提交",
            {"avid": avid, "task_id": task.id, "status": "pending", "file_size": None},
        )

    def delete(self, request, avid):
        """DELETE /api/downloads/{avid}: remove MP4 and clear database state."""
        _ = request
        try:
            result = resource_deletion_service.delete_video(avid)
        except ResourceTaskConflict as exc:
            return build_response(409, str(exc), None)
        except InvalidResourceIdentifier:
            return build_response(400, "avid 无效", None)
        except ResourceDeletionFailure as exc:
            return build_response(
                500,
                "删除未完成，请重试",
                {
                    "avid": avid.upper(),
                    "failed_stage": exc.stage,
                    "retryable": True,
                    "deleted_files": list(exc.deleted_files),
                },
            )
        if not result.found:
            return build_response(404, f"视频 {avid.upper()} 不存在", None)
        return build_response(
            200,
            "success",
            {
                "avid": avid.upper(),
                "deleted_file": result.deleted_files[0]
                if result.deleted_files
                else None,
                "file_size": result.file_size,
            },
        )


class TaskQueueStatusView(SchemaAPIView):
    """
    GET /api/tasks/queue/status
    获取当前任务队列状态

    返回完整的任务队列列表（从 Redis 获取），包括所有 PENDING 和 STARTED 状态的任务。
    解决了 Celery inspect() 只能获取部分任务的限制问题。
    """

    @extend_schema(
        operation_id="task_queue_status",
        summary="获取任务队列状态",
        description="返回任务队列的完整状态（含 PENDING 与 STARTED 任务）。",
        responses={
            200: OpenApiResponse(response=OpenApiTypes.OBJECT, description="成功"),
            500: OpenApiResponse(response=OpenApiTypes.OBJECT, description="获取失败"),
        },
        tags=["tasks"],
    )
    def get(self, request):
        from nassav.tasks import get_full_task_queue

        try:
            queue_status = get_full_task_queue()
            return build_response(200, "success", queue_status)
        except Exception as e:
            logger.error(f"获取任务队列状态失败: {e}")
            return build_response(500, f"获取队列状态失败: {e!s}", None)


class DownloadsBatchSubmitView(SchemaAPIView):
    """POST /api/downloads/batch_submit

    Body example: { "avids": ["ABC-123","DEF-222"] }
    """

    def post(self, request):
        data = request.data or {}
        avids = data.get("avids") or []
        results = []

        from nassav.tasks import submit_download_task

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
                    assert task_result is not None
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


class MockDownloadView(SchemaAPIView):
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
        from nassav.tasks import submit_mock_download_task

        try:
            task_result, is_duplicate = submit_mock_download_task(avid, duration)

            if is_duplicate:
                return build_response(409, "下载任务已存在", None)

            assert task_result is not None
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
            return build_response(500, f"提交失败: {e!s}", None)
