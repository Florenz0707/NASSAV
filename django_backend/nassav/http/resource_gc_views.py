"""Operator/admin-gated lifecycle metadata, without private titles or paths."""

from django.conf import settings
from nassav.http.account_views import AdminAccountView
from nassav.api_utils import build_response
from nassav.resource_gc import GcDeferred
from nassav.resource_gc_admin import GcAdminConflict
from nassav.resource_gc_records import DjangoGcRecords, gc_snapshot
from nassav.resource_gc_models import ResourceGcJob
from nassav.library_models import ResourcePoolEntry


class GcAdminView(AdminAccountView):
    def handle_exception(self, exc):
        if isinstance(exc, (GcAdminConflict, GcDeferred)):
            data: dict[str, object] = {"error_code": str(exc)}
            if isinstance(exc, GcDeferred):
                data["blockers"] = list(exc.reasons)
            return build_response(409, str(exc), data)
        if isinstance(exc, ValueError):
            return build_response(400, str(exc), None)
        if isinstance(exc, LookupError):
            return build_response(404, "对象不存在", None)
        return super().handle_exception(exc)

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not settings.SHARED_LIBRARY_ENABLED:
            raise PermissionError("Shared library is disabled")

    def command(self, request, action, target):
        from nassav.composition import build_resource_gc_administration

        if action in {"enqueue", "retry"} and not settings.RESOURCE_GC_ENABLED:
            return build_response(
                409, "回收执行开关尚未开启", {"error_code": "gc_not_enabled"}
            )
        result = build_resource_gc_administration().execute(
            request.user.pk, action, target, request.data
        )
        return build_response(200, "success", result)


class AdminResourcePoolsView(GcAdminView):
    def get(self, request):
        page = int(request.query_params.get("page", 1))
        size = int(request.query_params.get("page_size", 20))
        if page < 1 or not 1 <= size <= 100:
            raise ValueError("Invalid pagination")
        rows = ResourcePoolEntry.objects.order_by("-updated_at", "pk")
        data = [
            {
                "pool_id": str(row.pk),
                "avid": row.canonical_avid,
                "state": row.state,
                "pool_version": row.version,
                "generation": row.lifetime_generation,
                "retained": row.retained,
                "is_available": row.is_available,
                "gc_after": row.gc_after.isoformat() if row.gc_after else None,
            }
            for row in rows[(page - 1) * size : page * size]
        ]
        return build_response(
            200,
            "success",
            data,
            pagination={"page": page, "page_size": size, "total": rows.count()},
        )


class AdminGcPreviewView(GcAdminView):
    def get(self, request, pool_id):
        from uuid import UUID

        raw = request.query_params.get("version_id")
        result = DjangoGcRecords().preview(pool_id, UUID(raw) if raw else None)
        return build_response(200, "success", result)


class AdminGcEnqueueView(GcAdminView):
    def post(self, request, pool_id):
        return self.command(request, "enqueue", pool_id)


class AdminPoolRetentionView(GcAdminView):
    def put(self, request, pool_id):
        return self.command(request, "retention", pool_id)


class AdminGcJobsView(GcAdminView):
    def get(self, request):
        page = int(request.query_params.get("page", 1))
        size = int(request.query_params.get("page_size", 20))
        if page < 1 or not 1 <= size <= 100:
            raise ValueError("Invalid pagination")
        rows = ResourceGcJob.objects.select_related("pool").order_by(
            "-updated_at", "pk"
        )
        return build_response(
            200,
            "success",
            [gc_snapshot(row) for row in rows[(page - 1) * size : page * size]],
            pagination={"page": page, "page_size": size, "total": rows.count()},
        )


class AdminGcRetryView(GcAdminView):
    def post(self, request, job_id):
        return self.command(request, "retry", job_id)
