"""Authenticated external search submission and capability protected polling."""

from rest_framework import serializers

from nassav.api_utils import build_response
from nassav.http_base import SchemaAPIView
from nassav.models import Actor, Genre
from nassav.search_jobs import (
    SearchJobAlreadyFinished,
    SearchJobAccessExpired,
    cancel_search_job,
    get_search_job,
    search_job_token,
    submit_search_job,
    valid_search_job_token,
)
from nassav.source.search_contracts import SourceSearchUnavailable


class SearchQuerySerializer(serializers.Serializer):
    entity_type = serializers.ChoiceField(choices=["actor", "genre"])
    entity_id = serializers.IntegerField(min_value=1)
    page = serializers.IntegerField(min_value=1, default=1)
    page_size = serializers.IntegerField(min_value=1, max_value=100, default=20)
    ordering = serializers.CharField(default="-views")
    force_refresh = serializers.BooleanField(default=False)

    def get_fields(self):
        fields = super().get_fields()
        # `source` is also an attribute on DRF's Serializer base class.
        fields["source"] = serializers.ChoiceField(
            choices=["jable", "missav"], required=False
        )
        return fields


def public_snapshot(snapshot: dict) -> dict:
    return {
        key: value
        for key, value in snapshot.items()
        if key not in {"query_key", "collected_results", "owner_id", "owner_epoch"}
    }


class SearchJobSubmitView(SchemaAPIView):
    serializer_class = SearchQuerySerializer

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        if not serializer.is_valid():
            return build_response(400, "搜索参数无效", serializer.errors)
        try:
            snapshot, duplicate = submit_search_job(
                dict(serializer.validated_data), user_id=request.user.pk
            )
        except (Actor.DoesNotExist, Genre.DoesNotExist):
            return build_response(404, "搜索对象不存在", None)
        except ValueError as error:
            return build_response(400, str(error), None)
        except SourceSearchUnavailable:
            return build_response(503, "搜索源不可用", None)
        except Exception:
            return build_response(503, "搜索队列暂不可用，请稍后重试", None)
        data = {
            **public_snapshot(snapshot),
            "duplicate": duplicate,
            "token": search_job_token(snapshot["task_id"], user_id=request.user.pk),
        }
        return build_response(202, "搜索任务已提交", data)


class SearchJobStatusView(SchemaAPIView):
    def get(self, request, task_id):
        task_id = str(task_id)
        if not valid_search_job_token(
            task_id, request.query_params.get("token", ""), user_id=request.user.pk
        ):
            return build_response(403, "搜索任务访问凭证无效", None)
        try:
            page = request.query_params.get("page")
            page_size = request.query_params.get("page_size", 20)
            if page is not None and (int(page) < 1 or not 1 <= int(page_size) <= 100):
                raise ValueError("分页参数无效")
            snapshot = get_search_job(
                task_id,
                page=int(page) if page is not None else None,
                page_size=int(page_size),
            )
        except (ValueError, TypeError) as error:
            return build_response(400, str(error), None)
        except SearchJobAccessExpired as error:
            return build_response(410, str(error), None)
        except Exception:
            return build_response(503, "搜索任务状态暂不可用", None)
        if snapshot is None:
            return build_response(404, "搜索任务已过期或不存在，请重新搜索", None)
        from nassav.account_policy import execution_epoch

        if snapshot.get("owner_id") != request.user.pk or snapshot.get(
            "owner_epoch"
        ) != execution_epoch(request.user.pk):
            return build_response(404, "搜索任务不存在", None)
        return build_response(200, "success", public_snapshot(snapshot))


class SearchJobCancelView(SchemaAPIView):
    def post(self, request, task_id):
        if not isinstance(request.data, dict):
            return build_response(400, "请求必须为对象", None)
        task_id = str(task_id)
        if not valid_search_job_token(
            task_id, request.data.get("token", ""), user_id=request.user.pk
        ):
            return build_response(403, "搜索任务访问凭证无效", None)
        try:
            snapshot = get_search_job(task_id)
        except SearchJobAccessExpired as error:
            return build_response(410, str(error), None)
        except Exception:
            return build_response(503, "搜索任务状态暂不可用", None)
        from nassav.account_policy import execution_epoch

        if (
            snapshot is None
            or snapshot.get("owner_id") != request.user.pk
            or snapshot.get("owner_epoch") != execution_epoch(request.user.pk)
        ):
            return build_response(404, "搜索任务不存在", None)
        try:
            snapshot = cancel_search_job(task_id)
        except SearchJobAlreadyFinished:
            return build_response(409, "搜索任务已结束，无法取消", None)
        except (ValueError, TypeError) as error:
            return build_response(400, str(error), None)
        except Exception:
            return build_response(503, "搜索任务状态暂不可用", None)
        if snapshot is None:
            return build_response(404, "搜索任务已过期或不存在", None)
        return build_response(200, "搜索任务已取消", public_snapshot(snapshot))
