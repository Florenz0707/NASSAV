"""Shared schema support independent of concrete view modules."""

from rest_framework import serializers
from rest_framework.views import APIView


class EmptySchemaSerializer(serializers.Serializer):
    """Fallback serializer used only for OpenAPI schema generation."""


class SchemaAPIView(APIView):
    """Provide default serializer for drf-spectacular on plain APIViews."""

    serializer_class = EmptySchemaSerializer

    def handle_exception(self, exc):
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
