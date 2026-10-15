"""Old AVID-layout tools must never reinterpret scoped immutable assets."""


def require_legacy_layout():
    from django.conf import settings
    from django.core.management.base import CommandError
    from nassav.resource_version_models import ResourceVersion

    if settings.SHARED_LIBRARY_ENABLED or ResourceVersion.objects.exists():
        raise CommandError("旧布局修复工具不适用于范围版本；请使用版本校核/回收预览")
