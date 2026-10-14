"""Operator-gated explicit admin APIs; no implicit staff or superuser authority."""

from rest_framework.permissions import BasePermission
from nassav.http_base import SchemaAPIView
from nassav.api_utils import build_response
from nassav.account_management import AccountConflict
from nassav.account_policy import is_app_admin
from nassav.account_models import UserAccount, AuditEvent
from nassav.account_records import account_snapshot
from nassav.composition import build_account_management


class IsAdminOperator(BasePermission):
    def has_permission(self, request, view):
        from nassav.access import is_operator

        return is_operator(request.user) and is_app_admin(request.user)


class AdminAccountView(SchemaAPIView):
    permission_classes = [IsAdminOperator]

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "no-store"
        return response

    def execute(self, request, action, user_id=None):
        if not isinstance(request.data, dict):
            return build_response(400, "请求必须为对象", None)
        try:
            result = build_account_management().execute(
                request.user.pk, action, user_id, dict(request.data)
            )
            return build_response(201 if action == "create" else 200, "success", result)
        except ValueError as error:
            return build_response(400, str(error), None)
        except AccountConflict as error:
            return build_response(409, str(error), {"error_code": str(error)})
        except PermissionError:
            return build_response(403, "需要应用管理员权限", None)
        except LookupError:
            return build_response(404, "账号不存在", None)


class AdminUsersView(AdminAccountView):
    def get(self, request):
        try:
            page = int(request.query_params.get("page", 1))
            page_size = int(request.query_params.get("page_size", 20))
            if page < 1 or not 1 <= page_size <= 100:
                raise ValueError
        except (ValueError, TypeError):
            return build_response(400, "无效分页", None)
        rows = UserAccount.objects.select_related("user").order_by("user_id")
        return build_response(
            200,
            "success",
            [
                account_snapshot(row)
                for row in rows[(page - 1) * page_size : page * page_size]
            ],
            pagination={"page": page, "page_size": page_size, "total": rows.count()},
        )

    def post(self, request):
        return self.execute(request, "create")


class AdminUserView(AdminAccountView):
    def patch(self, request, user_id):
        return self.execute(request, "update", user_id)


class AdminSessionRevokeView(AdminAccountView):
    def post(self, request, user_id):
        return self.execute(request, "revoke_sessions", user_id)


class AdminPasswordResetView(AdminAccountView):
    def post(self, request, user_id):
        return self.execute(request, "reset_password", user_id)


class AdminAuditView(AdminAccountView):
    def get(self, request):
        rows = AuditEvent.objects.order_by("-created_at", "id")[:100]
        data = [
            {
                "id": str(row.pk),
                "actor_id": row.actor_id,
                "action": row.action,
                "object_id": row.object_id,
                "reason": row.reason,
                "result": row.result,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ]
        return build_response(200, "success", data)


class AdminResourceAvailabilityView(AdminAccountView):
    def post(self, request, pool_id):
        from nassav.resource_administration import set_availability
        from nassav.library_models import ResourcePoolEntry

        if not isinstance(request.data, dict):
            return build_response(400, "请求必须为对象", None)
        try:
            return build_response(
                200,
                "success",
                set_availability(request.user.pk, pool_id, dict(request.data)),
            )
        except ValueError as error:
            return build_response(400, str(error), None)
        except AccountConflict as error:
            return build_response(409, str(error), {"error_code": str(error)})
        except PermissionError:
            return build_response(403, "需要应用管理员权限", None)
        except ResourcePoolEntry.DoesNotExist:
            return build_response(404, "资源池不存在", None)
