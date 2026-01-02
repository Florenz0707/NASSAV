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
    title = LocalSerializerMethodField()  # 按优先级返回标题
    source = serializers.CharField(allow_blank=True)
    release_date = serializers.CharField(allow_blank=True)
    has_video = serializers.BooleanField(source='file_exists')
    metadata_create_time = LocalSerializerMethodField()
    video_create_time = LocalSerializerMethodField()
    genres = LocalSerializerMethodField()  # 类别列表
    thumbnail_url = LocalSerializerMethodField()

    def get_title(self, obj):
        """按优先级返回标题: translated_title > source_title > title"""
        if getattr(obj, 'translated_title', None):
            return obj.translated_title
        if getattr(obj, 'source_title', None):
            return obj.source_title
        return obj.title or ''

    def get_metadata_create_time(self, obj):
        return obj.metadata_saved_at.timestamp() if getattr(obj, 'metadata_saved_at', None) else None

    def get_video_create_time(self, obj):
        return obj.video_saved_at.timestamp() if getattr(obj, 'video_saved_at', None) else None

    def get_genres(self, obj):
        """获取类别列表"""
        try:
            return [g.name for g in obj.genres.all()]
        except Exception:
            return []

    def get_thumbnail_url(self, obj):
        try:
            from django.conf import settings
            from pathlib import Path
            cover_root = Path(settings.COVER_DIR)
            cover_name = obj.cover_filename or f"{obj.avid}.jpg"
            cover_path = cover_root / cover_name
            if cover_path.exists():
                v = int(cover_path.stat().st_mtime)
                return f"/nassav/api/resource/cover?avid={obj.avid}&size=medium&v={v}"
            else:
                return f"/nassav/api/resource/cover?avid={obj.avid}&size=medium"
        except Exception:
            return f"/nassav/api/resource/cover?avid={obj.avid}&size=medium"


class ResourceSerializer(serializers.Serializer):
    """完整资源元数据序列化器（用于 detail/metadata）"""
    avid = serializers.CharField()
    title = LocalSerializerMethodField()  # 按优先级返回标题
    original_title = LocalSerializerMethodField()  # 原始日语标题
    source_title = serializers.CharField(allow_blank=True, allow_null=True, required=False)
    translated_title = serializers.CharField(allow_blank=True, allow_null=True, required=False)
    translation_status = serializers.CharField(allow_blank=True, required=False)  # 翻译状态
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

    def get_title(self, obj):
        """按优先级返回标题: translated_title > source_title > original_title"""
        if isinstance(obj, dict):
            if obj.get('translated_title'):
                return obj['translated_title']
            if obj.get('source_title'):
                return obj['source_title']
            return obj.get('title', '')
        else:
            if getattr(obj, 'translated_title', None):
                return obj.translated_title
            if getattr(obj, 'source_title', None):
                return obj.source_title
            return obj.title or ''

    def get_original_title(self, obj):
        """返回原始日语标题（Scraper 获取的标题）"""
        if isinstance(obj, dict):
            return obj.get('title', '')
        return obj.title or ''


class ResourceCreateSerializer(serializers.Serializer):
    """用于创建资源的输入校验序列化器"""
    avid = serializers.CharField(max_length=50)
    source = serializers.CharField(max_length=128, default='any', required=False)

    def validate_avid(self, value):
        return value.strip().upper()
