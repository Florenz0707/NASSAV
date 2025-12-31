from rest_framework import serializers
from rest_framework.fields import Field

from .models import AVResource


# Local SerializerMethodField implementation to avoid site-packages corruption
class LocalSerializerMethodField(Field):
    def __init__(self, method_name=None, **kwargs):
        self.method_name = method_name
        kwargs['read_only'] = True
        super().__init__(**kwargs)

    def bind(self, field_name, parent):
        if self.method_name is None:
            self.method_name = f'get_{field_name}'
        super().bind(field_name, parent)

    def to_representation(self, value):
        method = getattr(self.parent, self.method_name)
        return method(value)

    def get_attribute(self, instance):
        # Always pass the root object to the method, ignore source lookups
        return instance


class NewResourceSerializer(serializers.Serializer):
    """新增资源请求序列化器"""
    avid = serializers.CharField(max_length=50)
    source = serializers.CharField(max_length=50, default='any', required=False)


class DownloadRequestSerializer(serializers.Serializer):
    """下载请求序列化器"""
    avid = serializers.CharField(max_length=50)


class SourceCookieSerializer(serializers.Serializer):
    """设置源Cookie请求序列化器"""
    source = serializers.CharField(max_length=50)
    cookie = serializers.CharField()


class ResourceSummarySerializer(serializers.Serializer):
    """列表视图使用的资源摘要序列化器（显式字段，避免 ModelSerializer 自动映射）"""
    avid = serializers.CharField()
    title = serializers.CharField(allow_blank=True)
    source = serializers.CharField(allow_blank=True)
    release_date = serializers.CharField(allow_blank=True)
    has_video = serializers.BooleanField(source='file_exists')
    metadata_create_time = LocalSerializerMethodField()
    video_create_time = LocalSerializerMethodField()
    file_size = serializers.IntegerField(allow_null=True)

    def get_metadata_create_time(self, obj):
        return obj.metadata_saved_at.timestamp() if getattr(obj, 'metadata_saved_at', None) else None

    def get_video_create_time(self, obj):
        return obj.video_saved_at.timestamp() if getattr(obj, 'video_saved_at', None) else None


class ResourceSerializer(serializers.Serializer):
    """完整资源元数据序列化器（用于 detail/metadata）"""
    avid = serializers.CharField()
    title = serializers.CharField(allow_blank=True)
    m3u8 = serializers.CharField(allow_blank=True, allow_null=True, required=False)
    source = serializers.CharField(allow_blank=True, required=False)
    release_date = serializers.CharField(allow_blank=True, required=False)
    duration = serializers.IntegerField(allow_null=True, required=False)
    director = serializers.CharField(allow_blank=True, required=False)
    studio = serializers.CharField(allow_blank=True, required=False)
    label = serializers.CharField(allow_blank=True, required=False)
    series = serializers.CharField(allow_blank=True, required=False)
    actors = serializers.ListField(child=serializers.CharField(), allow_empty=True, required=False)
    genres = serializers.ListField(child=serializers.CharField(), allow_empty=True, required=False)
    file_size = serializers.IntegerField(allow_null=True, required=False)
    file_exists = serializers.BooleanField(required=False)


class ResourceCreateSerializer(serializers.Serializer):
    """用于创建资源的输入校验序列化器"""
    avid = serializers.CharField(max_length=50)
    source = serializers.CharField(max_length=128, default='any', required=False)

    def validate_avid(self, value):
        return value.strip().upper()
