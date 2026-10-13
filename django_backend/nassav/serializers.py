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
    """Flat API fields derived from the canonical definitions, independent of JSON storage."""

    def get_fields(self):
        from nassav.preference_definitions import PREFERENCE_DEFINITIONS

        fields: dict[str, serializers.Field] = {}
        for key, definition in PREFERENCE_DEFINITIONS.items():
            default = definition.default
            if definition.choices:
                fields[key] = serializers.ChoiceField(choices=definition.choices)
            elif isinstance(default, str):
                if definition.max_length is None:
                    fields[key] = serializers.CharField(trim_whitespace=False)
                else:
                    fields[key] = serializers.CharField(
                        max_length=definition.max_length, trim_whitespace=False
                    )
            elif isinstance(default, bool):
                fields[key] = serializers.BooleanField()
            elif isinstance(default, int):
                fields[key] = serializers.IntegerField()
            else:
                fields[key] = serializers.FloatField()
        return fields


class UserSettingUpdateSerializer(UserSettingSerializer):
    """Strict partial updates; removed/unknown keys cannot be written."""

    def get_fields(self):
        fields = super().get_fields()
        for field in fields.values():
            field.required = False
        from nassav.external_search import external_search_service

        source_field = fields.get("default_external_search_source")
        if isinstance(source_field, serializers.ChoiceField):
            source_field.choices = [
                entry["source"] for entry in external_search_service.capabilities()
            ]
        return fields

    def to_internal_value(self, data):
        from nassav.preference_definitions import (
            InvalidPreference,
            validate_preferences,
        )

        try:
            validate_preferences(data)
        except InvalidPreference as error:
            detail = (
                {error.key: str(error)}
                if error.key is not None
                else {"non_field_errors": [str(error)]}
            )
            raise serializers.ValidationError(detail) from error
        return super().to_internal_value(data)


class ResourceSummarySerializer(serializers.Serializer):
    """列表视图使用的资源摘要序列化器（显式字段，避免 ModelSerializer 自动映射）"""

    avid = serializers.CharField()
    original_title = serializers.CharField(allow_blank=True)
    source_title = serializers.CharField(allow_blank=True, allow_null=True)
    translated_title = serializers.CharField(allow_blank=True, allow_null=True)
    source = serializers.CharField(allow_blank=True)  # type: ignore
    release_date = serializers.CharField(allow_blank=True)
    has_video = serializers.BooleanField(source="file_exists")
    watched = serializers.BooleanField(source="personal_watched", default=False)
    is_favorite = serializers.BooleanField(source="personal_is_favorite", default=False)
    state_version = serializers.IntegerField(source="personal_state_version", default=0)
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


class StrictBooleanField(serializers.BooleanField):
    def to_internal_value(self, data):
        if not isinstance(data, bool):
            raise serializers.ValidationError("必须是布尔值")
        return data


class ResourceStatusUpdateSerializer(serializers.Serializer):
    watched = StrictBooleanField(required=False)
    is_favorite = StrictBooleanField(required=False)
    notes = serializers.CharField(
        required=False, allow_blank=True, max_length=5000, trim_whitespace=False
    )
    expected_version = serializers.IntegerField(required=False, min_value=0)

    def validate(self, attrs):
        unknown = set(self.initial_data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError("存在不支持的个人状态字段")
        if not ({"watched", "is_favorite", "notes"} & set(attrs)):
            raise serializers.ValidationError("未提供任何要更新的字段")
        if "notes" in self.initial_data and not isinstance(
            self.initial_data["notes"], str
        ):
            raise serializers.ValidationError({"notes": "备注必须是文本"})
        version = self.initial_data.get("expected_version")
        if version is not None and (
            not isinstance(version, int) or isinstance(version, bool)
        ):
            raise serializers.ValidationError(
                {"expected_version": "版本必须是非负整数"}
            )
        return attrs
