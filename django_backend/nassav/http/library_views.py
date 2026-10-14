"""Shared library commands expose only the current user's durable demand."""

from django.conf import settings
from rest_framework.permissions import BasePermission

from nassav.access import is_operator
from nassav.account_policy import account
from nassav.api_utils import build_response
from nassav.http_base import SchemaAPIView
from nassav import composition
from nassav.library_models import UserLibraryEntry
from nassav.library_membership import LibraryConflict, LibraryNotFound
from nassav.shared_work import SharedOperations, OperationConflict, OperationNotFound


class LibraryAdmission(BasePermission):
    def has_permission(self, request, view):
        return (
            settings.SHARED_LIBRARY_ENABLED
            and is_operator(request.user)
            and account(request.user) is not None
        )


class LibraryAPIView(SchemaAPIView):
    permission_classes = [LibraryAdmission]

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        response["Vary"] = "Cookie"
        return response

    def handle_exception(self, exc):
        if isinstance(exc, PermissionError) and str(exc) == "quota_exceeded":
            from nassav.quota_records import logical_used_bytes

            role = account(self.request.user)
            return build_response(
                403,
                "个人配额不足",
                {
                    "error_code": "quota_exceeded",
                    "storage_quota_bytes": role.storage_quota_bytes if role else None,
                    "used_bytes": logical_used_bytes(self.request.user.pk),
                    "max_active_operations": role.max_active_operations
                    if role
                    else None,
                },
            )
        if isinstance(exc, (LibraryNotFound, OperationNotFound)):
            return build_response(404, "对象不存在", None)
        if isinstance(exc, (LibraryConflict, OperationConflict)):
            return build_response(409, str(exc), {"error_code": str(exc)})
        if isinstance(exc, ValueError):
            return build_response(400, str(exc), None)
        return super().handle_exception(exc)


class LibraryEntriesView(LibraryAPIView):
    def post(self, request):
        if (
            not isinstance(request.data, dict)
            or request.data.get("kind", "scrape") != "scrape"
            or request.data.get("action", "add") != "add"
        ):
            raise ValueError("Use add for a new library entry")
        payload = {**request.data, "kind": "scrape", "action": "add"}
        operation = composition.build_library_submission().submit(
            request.user.pk, payload
        )
        entry = UserLibraryEntry.objects.filter(
            user_id=request.user.pk, pool__canonical_avid=operation["avid"]
        ).first()
        return build_response(
            202 if operation["state"] != "succeeded" else 200,
            "success",
            {
                "entry_id": str(entry.pk) if entry else None,
                "entry_version": entry.version if entry else None,
                "membership_state": entry.state if entry else None,
                "is_in_my_library": entry is not None,
                "reused": operation["state"] == "succeeded",
                "operation": operation,
            },
        )


class LibraryEntryView(LibraryAPIView):
    def delete(self, request, entry_id):
        if not isinstance(request.data, dict) or set(request.data) != {
            "expected_version",
            "request_id",
        }:
            raise ValueError("Provide expected_version and request_id")
        result = composition.build_library_membership().release(
            request.user.pk,
            entry_id,
            expected_version=request.data["expected_version"],
            request_id=request.data["request_id"],
        )
        return build_response(200, "success", result)


class LibraryEntryOperationsView(LibraryAPIView):
    def post(self, request, entry_id):
        entry = (
            UserLibraryEntry.objects.filter(pk=entry_id, user_id=request.user.pk)
            .select_related("pool")
            .first()
        )
        if entry is None:
            raise LibraryNotFound("Object not available")
        if (
            not isinstance(request.data, dict)
            or "avid" in request.data
            or "expected_entry_version" not in request.data
            or (request.data.get("kind"), request.data.get("action"))
            not in {("scrape", "refresh"), ("download", "download")}
        ):
            raise ValueError(
                "Provide operation and expected_entry_version without avid"
            )
        payload = {**request.data, "avid": entry.pool.canonical_avid}
        result = composition.build_library_submission().submit(request.user.pk, payload)
        return build_response(
            202 if result["state"] != "succeeded" else 200, "success", result
        )


class MyOperationView(LibraryAPIView):
    def get(self, request, operation_id):
        result = composition.build_operation_records().project(
            request.user.pk, operation_id
        )
        return build_response(200, "success", result)


class MyOperationCancelView(LibraryAPIView):
    def post(self, request, operation_id):
        if not isinstance(request.data, dict) or set(request.data) != {
            "expected_version",
            "request_id",
        }:
            raise ValueError("Provide expected_version and request_id")
        result = SharedOperations(composition.build_operation_records()).cancel(
            request.user.pk,
            operation_id,
            expected_version=request.data["expected_version"],
            request_id=request.data["request_id"],
        )
        return build_response(200, "success", result)


class MyOperationsView(LibraryAPIView):
    def get(self, request):
        from django.core.paginator import Paginator
        from nassav.shared_work_models import UserOperation
        from nassav.shared_work_records import operation_snapshot

        ordering = request.query_params.get("ordering", "-updated_at")
        if ordering not in {"-created_at", "-updated_at"}:
            raise ValueError("Use descending creation/update ordering")
        try:
            size = int(request.query_params.get("page_size", 20))
            page = int(request.query_params.get("page", 1))
        except (ValueError, TypeError):
            raise ValueError("Invalid pagination") from None
        if not 1 <= size <= 100 or page < 1:
            raise ValueError("Invalid pagination")
        rows = (
            UserOperation.objects.filter(user_id=request.user.pk)
            .select_related("pool")
            .order_by(ordering, "-pk")
        )
        state = request.query_params.get("state")
        if state:
            if state not in {
                "queued",
                "running",
                "pausing",
                "paused",
                "cancelling",
                "succeeded",
                "failed",
                "cancelled",
            }:
                raise ValueError("Invalid operation state")
            rows = rows.filter(state=state)
        paginator = Paginator(rows, size)
        selected = paginator.get_page(page)
        return build_response(
            200,
            "success",
            [operation_snapshot(row) for row in selected.object_list],
            pagination={
                "total": paginator.count,
                "page": selected.number,
                "page_size": size,
                "pages": paginator.num_pages,
            },
        )
