"""Owner-authorized submission, polling and cancellation of recommendations."""

from rest_framework import serializers
from nassav.api_utils import build_response
from nassav.http_base import SchemaAPIView
from nassav.recommendation import jobs
from nassav.recommendation_models import RecommendationJob
from nassav.recommendation.workflow import RecommendationManagerError
from nassav.http_parameters import _parse_recommendation_request_params


class RecommendationQuerySerializer(serializers.Serializer):
    strategy = serializers.ChoiceField(
        choices=["local_preference"], default="local_preference"
    )
    limit = serializers.IntegerField(min_value=1, max_value=100, default=12)
    per_seed_limit = serializers.IntegerField(min_value=1, max_value=100, default=12)
    actor_seed_limit = serializers.IntegerField(min_value=1, max_value=20, default=5)
    genre_seed_limit = serializers.IntegerField(min_value=1, max_value=20, default=5)
    discovery_limit = serializers.IntegerField(min_value=1, max_value=100, default=12)
    detail_enrichment_limit = serializers.IntegerField(
        min_value=1, max_value=100, default=24
    )
    recent_snapshot_limit = serializers.IntegerField(
        min_value=1, max_value=100, default=3
    )
    recent_item_limit = serializers.IntegerField(min_value=1, max_value=300, default=36)
    exclude_existing = serializers.BooleanField(default=True)
    avoid_recent_recommendations = serializers.BooleanField(default=True)
    include_hot_board = serializers.BooleanField(default=True)
    include_latest_updates = serializers.BooleanField(default=True)
    force_refresh_external = serializers.BooleanField(default=False)
    type_preference = serializers.ChoiceField(
        choices=["actor_heavy", "balanced", "genre_heavy"], default="balanced"
    )
    actor_preference = serializers.ChoiceField(
        choices=["familiar", "balanced", "rare"], default="balanced"
    )
    genre_preference = serializers.ChoiceField(
        choices=["familiar", "balanced", "rare"], default="balanced"
    )


class RecommendationJobSubmitView(SchemaAPIView):
    serializer_class = RecommendationQuerySerializer

    def post(self, request):
        from nassav.personal_preferences import read_preferences

        preferences = read_preferences(request.user.pk)
        defaults = {
            key: preferences[f"recommendation_{key}"]
            for key in (
                "type_preference",
                "actor_preference",
                "genre_preference",
                "limit",
            )
        }
        serializer = self.serializer_class(data={**defaults, **request.data})
        if not serializer.is_valid():
            return build_response(400, "推荐参数无效", serializer.errors)
        payload = dict(serializer.validated_data)
        parameters = _parse_recommendation_request_params(payload)
        parameters["strategy"] = payload["strategy"]
        try:
            job = jobs.submit(request.user, parameters)
        except jobs.RecommendationStopped:
            return build_response(409, "推荐历史已重置，请重试", None)
        except RecommendationManagerError:
            return build_response(400, "推荐参数无效", None)
        return build_response(202, "推荐任务已提交", jobs.snapshot(job))


class RecommendationJobStatusView(SchemaAPIView):
    def get(self, request, job_id):
        jobs.recover_expired()
        job = RecommendationJob.objects.filter(pk=job_id, owner=request.user).first()
        if job is None:
            return build_response(404, "推荐任务不存在", None)
        return build_response(200, "success", jobs.snapshot(job))


class RecommendationJobCancelView(SchemaAPIView):
    def post(self, request, job_id):
        job = jobs.cancel(job_id, request.user)
        if job is None:
            return build_response(404, "推荐任务不存在", None)
        return build_response(200, "success", jobs.snapshot(job))
