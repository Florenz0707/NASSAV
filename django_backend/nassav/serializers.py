from rest_framework import serializers
from rest_framework.fields import Field

from .models import AVResource


# Local SerializerMethodField implementation to avoid site-packages corruption
class LocalSerializerMethodField(Field):
    def __init__(self, method_name=None, **kwargs):
        self.method_name = method_name
        kwargs["read_only"] = True
        super().__init__(**kwargs)

    def bind(self, field_name, parent):
        if self.method_name is None:
            self.method_name = f"get_{field_name}"
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
    source = serializers.CharField(max_length=50, default="any", required=False)


class DownloadRequestSerializer(serializers.Serializer):
    """下载请求序列化器"""

    avid = serializers.CharField(max_length=50)


class SourceCookieSerializer(serializers.Serializer):
    """设置源Cookie请求序列化器"""

    source = serializers.CharField(max_length=50)
    cookie = serializers.CharField()


class SourceCookieListSerializer(serializers.Serializer):
    """获取源Cookie列表序列化器"""

    source = serializers.CharField(source="source_name")
    cookie = serializers.CharField()
    mtime = serializers.DateTimeField(source="updated_at")


class UserSettingSerializer(serializers.Serializer):
    """用户设置序列化器"""

    enable_avatar = serializers.CharField()
    display_title = serializers.CharField()


class UserSettingUpdateSerializer(serializers.Serializer):
    """用户设置更新序列化器"""

    enable_avatar = serializers.CharField(required=False)
    display_title = serializers.CharField(required=False)

    def validate_enable_avatar(self, value):
        """验证 enable_avatar 值"""
        if value not in ["true", "false"]:
            raise serializers.ValidationError("enable_avatar 必须是 'true' 或 'false'")
        return value

    def validate_display_title(self, value):
        """验证 display_title 值"""
        valid_values = ["original_title", "source_title", "translated_title"]
        if value not in valid_values:
            raise serializers.ValidationError(
                f"display_title 必须是 {', '.join(valid_values)} 之一"
            )
        return value


class ResourceSummarySerializer(serializers.Serializer):
    """列表视图使用的资源摘要序列化器（显式字段，避免 ModelSerializer 自动映射）"""

    avid = serializers.CharField()
    original_title = serializers.CharField(allow_blank=True)
    source_title = serializers.CharField(allow_blank=True, allow_null=True)
    translated_title = serializers.CharField(allow_blank=True, allow_null=True)
    source = serializers.CharField(allow_blank=True)
    release_date = serializers.CharField(allow_blank=True)
    has_video = serializers.BooleanField(source="file_exists")
    watched = serializers.BooleanField()
    is_favorite = serializers.BooleanField()
    metadata_create_time = LocalSerializerMethodField()
    metadata_update_time = LocalSerializerMethodField()
    video_create_time = LocalSerializerMethodField()
    genres = LocalSerializerMethodField()  # 类别列表
    thumbnail_url = LocalSerializerMethodField()

    def get_metadata_create_time(self, obj):
        return (
            obj.metadata_created_at.timestamp()
            if getattr(obj, "metadata_created_at", None)
            else None
        )

    def get_metadata_update_time(self, obj):
        return (
            obj.metadata_updated_at.timestamp()
            if getattr(obj, "metadata_updated_at", None)
            else None
        )

    def get_video_create_time(self, obj):
        return (
            obj.video_saved_at.timestamp()
            if getattr(obj, "video_saved_at", None)
            else None
        )

    def get_genres(self, obj):
        """获取类别列表"""
        try:
            return [g.name for g in obj.genres.all()]
        except Exception:
            return []

    def get_thumbnail_url(self, obj):
        try:
            from pathlib import Path

            from django.conf import settings

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
    original_title = serializers.CharField(allow_blank=True, required=False)
    source_title = serializers.CharField(
        allow_blank=True, allow_null=True, required=False
    )
    translated_title = serializers.CharField(
        allow_blank=True, allow_null=True, required=False
    )
    translation_status = serializers.CharField(allow_blank=True, required=False)  # 翻译状态
    m3u8 = serializers.CharField(allow_blank=True, allow_null=True, required=False)
    source = serializers.CharField(allow_blank=True, required=False)
    release_date = serializers.CharField(allow_blank=True, required=False)
    duration = serializers.IntegerField(allow_null=True, required=False)
    director = serializers.CharField(allow_blank=True, required=False)
    studio = serializers.CharField(allow_blank=True, required=False)
    label = serializers.CharField(allow_blank=True, required=False)
    series = serializers.CharField(allow_blank=True, required=False)
    actors = serializers.ListField(
        child=serializers.CharField(), allow_empty=True, required=False
    )
    genres = serializers.ListField(
        child=serializers.CharField(), allow_empty=True, required=False
    )
    file_size = serializers.IntegerField(allow_null=True, required=False)
    file_exists = serializers.BooleanField(required=False)
    watched = serializers.BooleanField(required=False)
    is_favorite = serializers.BooleanField(required=False)


class ResourceCreateSerializer(serializers.Serializer):
    """用于创建资源的输入校验序列化器"""

    avid = serializers.CharField(max_length=50)
    source = serializers.CharField(max_length=128, default="any", required=False)

    def validate_avid(self, value):
        return value.strip().upper()
