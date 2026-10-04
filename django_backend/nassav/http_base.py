"""Shared schema support independent of concrete view modules."""

from rest_framework import serializers
from rest_framework.views import APIView


class EmptySchemaSerializer(serializers.Serializer):
    """Fallback serializer used only for OpenAPI schema generation."""


class SchemaAPIView(APIView):
    """Provide default serializer for drf-spectacular on plain APIViews."""

    serializer_class = EmptySchemaSerializer
