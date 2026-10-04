"""
API视图：实现资源管理接口
所有信息以 resource 目录中的实际资源为准
统一响应格式: {"code": xxx, "message": xxx, "data": data}
"""

from loguru import logger
from rest_framework import status
from rest_framework.response import Response

from nassav.serializers import (
    UserSettingSerializer,
    UserSettingUpdateSerializer,
)


from nassav.http_base import SchemaAPIView


class UserSettingView(SchemaAPIView):
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
