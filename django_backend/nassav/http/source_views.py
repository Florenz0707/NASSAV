"""
API视图：实现资源管理接口
所有信息以 resource 目录中的实际资源为准
统一响应格式: {"code": xxx, "message": xxx, "data": data}
"""

from loguru import logger
from rest_framework import status
from rest_framework.response import Response

from nassav.api_utils import build_response
from nassav.external_search import external_search_service
from nassav.http_base import SchemaAPIView
from nassav.serializers import (
    SourceCookieListSerializer,
)
from nassav.source.SourceManager import source_manager


class SourceListView(SchemaAPIView):
    """
    GET /api/source/list
    获取所有可用的下载源名称列表
    """

    def get(self, request):
        sources = [name for name, _ in source_manager.get_sources()]
        return Response({"code": 200, "message": "success", "data": sources})


class SourceSearchCapabilitiesView(SchemaAPIView):
    """Enabled source capabilities for actor and genre external search."""

    def get(self, request):
        return build_response(200, "success", external_search_service.capabilities())


class SourceCookieView(SchemaAPIView):
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
      - user_agent: 手动 Cookie 配套 User-Agent (optional)
      - auto: 是否自动获取 cookie (boolean, optional)
    """

    def get(self, request):
        """获取所有源的 Cookie 配置"""
        from nassav.models import SourceCookie

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

        # 所有同步 API 与 worker 使用同一站点会话刷新协调器。
        if auto:
            try:
                if not source_manager.get_source(source_name):
                    return Response(
                        {
                            "code": 404,
                            "message": f"无法获取 {source_name} 实例",
                            "data": None,
                        },
                        status=status.HTTP_404_NOT_FOUND,
                    )
                if source_manager.auto_source_cookie(source_name):
                    return Response(
                        {
                            "code": 200,
                            "message": "Cookie 自动获取成功",
                            "data": {"source": source_name, "cookie_set": True},
                        }
                    )
                return Response(
                    {"code": 500, "message": "Cookie 自动获取失败", "data": None},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )
            except Exception as error:
                logger.error(f"自动获取 Cookie 异常: {type(error).__name__}")
                return Response(
                    {"code": 500, "message": "Cookie 自动获取失败", "data": None},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

        # 否则如果提供了 cookie 则手动设置并保存到 DB
        if cookie:
            user_agent = data.get("user_agent")
            if user_agent is not None and (
                not isinstance(user_agent, str) or len(user_agent) > 4096
            ):
                return Response(
                    {"code": 400, "message": "user_agent 参数无效", "data": None},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            success = source_manager.set_source_cookie(
                source_name, cookie, user_agent=user_agent or None
            )
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
            {
                "code": 400,
                "message": "未提供 cookie 且 auto 未设置为 True",
                "data": None,
            },
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
