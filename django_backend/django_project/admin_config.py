"""The managed application owns account commands, last-admin protection and audit."""

from django.conf import settings
from django.contrib.admin.apps import AdminConfig
from django.contrib.admin.sites import AdminSite
from django.http import HttpResponseNotFound


class NassavAdminSite(AdminSite):
    def has_permission(self, request):
        # Stock auth.User forms bypass app role/version/audit/revocation commands.
        return not settings.MULTI_USER_ENABLED and super().has_permission(request)

    def login(self, request, extra_context=None):
        if settings.MULTI_USER_ENABLED:
            response = HttpResponseNotFound("多用户模式请使用应用管理中心")
            response["Cache-Control"] = "no-store"
            return response
        return super().login(request, extra_context)


class NassavAdminConfig(AdminConfig):
    default_site = "django_project.admin_config.NassavAdminSite"
