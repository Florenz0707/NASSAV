"""Shared schema support independent of concrete view modules."""

from rest_framework import serializers
from rest_framework.views import APIView


class EmptySchemaSerializer(serializers.Serializer):
    """Fallback serializer used only for OpenAPI schema generation."""


class SchemaAPIView(APIView):
    """Provide default serializer for drf-spectacular on plain APIViews."""

    serializer_class = EmptySchemaSerializer

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        from django.conf import settings
        from django.utils.cache import patch_vary_headers

        if settings.MULTI_USER_ENABLED or response.status_code >= 400:
            if not getattr(response, "_nassav_revalidated_image", False):
                response["Cache-Control"] = "private, no-store"
            patch_vary_headers(response, ["Cookie"])
        return response

    def perform_authentication(self, request):
        super().perform_authentication(request)
        from nassav.browser_context import require_browser_context

        require_browser_context(request)

    def handle_exception(self, exc):
        from nassav.browser_context import BrowserContextChanged

        if isinstance(exc, BrowserContextChanged):
            from nassav.api_utils import build_response

            return build_response(
                409, str(exc.detail), {"error_code": "browser_context_changed"}
            )
        from nassav.library_membership import LibraryNotFound
        from nassav.api_utils import build_response
        from nassav.credential_crypto import CredentialUnavailable
        from nassav.resource_reads import ReadLeaseNotFound, ReadLeaseConflict

        if isinstance(exc, ReadLeaseNotFound):
            return build_response(404, "对象不存在", None)
        if isinstance(exc, ReadLeaseConflict):
            return build_response(409, str(exc), None)

        if isinstance(exc, LibraryNotFound):
            return build_response(404, "对象不存在", None)
        if isinstance(exc, PermissionError):
            return build_response(403, "操作未授权或账号已停用", None)
        if isinstance(exc, CredentialUnavailable):
            return build_response(503, str(exc), None)
        return super().handle_exception(exc)
