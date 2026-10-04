from rest_framework import serializers
from rest_framework.fields import Field


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
        method = getattr(self.parent, self.method_name)  # type: ignore
        return method(value)

    def get_attribute(self, instance):
        # Always pass the root object to the method, ignore source lookups
        return instance


class NewResourceSerializer(serializers.Serializer):
    """新增资源请求序列化器"""

    avid = serializers.CharField(max_length=50)
    source = serializers.CharField(max_length=50, default="any", required=False)  # type: ignore


class SourceCookieListSerializer(serializers.Serializer):
    """获取源Cookie列表序列化器"""

    source = serializers.CharField(source="source_name")  # type: ignore
    cookie = serializers.CharField()  # type: ignore
    mtime = serializers.DateTimeField(source="updated_at")
    session_source = LocalSerializerMethodField()
    user_agent_paired = LocalSerializerMethodField()
    session_expired = LocalSerializerMethodField()
    verified_direct_reuse = LocalSerializerMethodField()

    def get_session_source(self, obj):
        return "verified_browser" if obj.egress_profile and obj.user_agent else "manual"

    def get_user_agent_paired(self, obj):
        return bool(obj.user_agent)

    def get_session_expired(self, obj):
        from django.utils import timezone

        return bool(obj.expires_at and obj.expires_at <= timezone.now())

    def get_verified_direct_reuse(self, obj):
        from nassav.source.CookieRepository import proxy_route_profile
        from nassav.source.SourceManager import source_manager

        source = source_manager.get_source(obj.source_name)
        route = proxy_route_profile(source.proxy) if source else None
        return bool(
            obj.cookie
            and obj.user_agent
            and obj.egress_profile
            and obj.egress_profile == route
            and not self.get_session_expired(obj)
        )


class UserSettingSerializer(serializers.Serializer):
    """用户设置序列化器"""

    enable_avatar = serializers.CharField()
    display_title = serializers.CharField()
    font_family = serializers.CharField()
    color_mode = serializers.CharField()
    search_result_display_style = serializers.CharField()
    default_external_search_source = serializers.CharField()


class UserSettingUpdateSerializer(serializers.Serializer):
    """用户设置更新序列化器"""

    enable_avatar = serializers.CharField(required=False)
    display_title = serializers.CharField(required=False)
    font_family = serializers.CharField(required=False)
    color_mode = serializers.CharField(required=False)
    search_result_display_style = serializers.CharField(required=False)
    default_external_search_source = serializers.ChoiceField(
        choices=["jable", "missav"], required=False
    )

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

    def validate_color_mode(self, value):
        """验证 color_mode 值"""
        valid_values = ["light", "dark"]
        if value not in valid_values:
            raise serializers.ValidationError(
                f"color_mode 必须是 {', '.join(valid_values)} 之一"
            )
        return value

    def validate_search_result_display_style(self, value):
        """验证搜索结果展示样式"""
        valid_values = ["grid", "masonry"]
        if value not in valid_values:
            raise serializers.ValidationError(
                "search_result_display_style 必须是 grid, masonry 之一"
            )
        return value


class ResourceSummarySerializer(serializers.Serializer):
    """列表视图使用的资源摘要序列化器（显式字段，避免 ModelSerializer 自动映射）"""

    avid = serializers.CharField()
    original_title = serializers.CharField(allow_blank=True)
    source_title = serializers.CharField(allow_blank=True, allow_null=True)
    translated_title = serializers.CharField(allow_blank=True, allow_null=True)
    source = serializers.CharField(allow_blank=True)  # type: ignore
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


class ResourceJobSerializer(serializers.Serializer):
    """Validate one asynchronous add or refresh request."""

    action = serializers.ChoiceField(choices=["add", "refresh"])
    avid = serializers.CharField(max_length=50, trim_whitespace=True)
    source = serializers.CharField(max_length=50, default="any", required=False)  # type: ignore
    refresh_m3u8 = serializers.BooleanField(default=True, required=False)
    refresh_metadata = serializers.BooleanField(default=True, required=False)
    retranslate = serializers.BooleanField(default=False, required=False)
