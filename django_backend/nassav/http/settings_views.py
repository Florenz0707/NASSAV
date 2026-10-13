"""
API视图：实现资源管理接口
所有信息以 resource 目录中的实际资源为准
统一响应格式: {"code": xxx, "message": xxx, "data": data}
"""

from loguru import logger
from rest_framework import status
from rest_framework.response import Response

from nassav.http_base import SchemaAPIView
from nassav.serializers import (
    UserSettingSerializer,
    UserSettingUpdateSerializer,
)


class UserSettingView(SchemaAPIView):
    """
    GET /api/setting
    获取用户设置。

    PUT /api/setting
    更新用户设置。
    """

    def get(self, request):
        """获取所有用户设置"""
        from nassav.personal_preferences import read_preferences

        try:
            settings = read_preferences(request.user.pk)
            serializer = UserSettingSerializer(settings)
            return Response(
                {"code": 200, "message": "success", "data": serializer.data},
                headers={"Cache-Control": "private, no-store"},
            )
        except Exception as e:
            logger.error(f"获取用户设置失败: {e}")
            return Response(
                {"code": 500, "message": f"获取设置失败: {e!s}", "data": None},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def put(self, request):
        """更新用户设置"""
        from nassav.personal_preferences import update_preferences

        serializer = UserSettingUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"code": 400, "message": "参数验证失败", "data": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            updated_settings = update_preferences(
                request.user.pk, dict(serializer.validated_data)
            )
            return Response(
                {
                    "code": 200,
                    "message": "设置已更新",
                    "data": UserSettingSerializer(updated_settings).data,
                },
                headers={"Cache-Control": "private, no-store"},
            )
        except Exception as e:
            logger.error(f"更新用户设置失败: {e}")
            return Response(
                {"code": 500, "message": f"更新设置失败: {e!s}", "data": None},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
