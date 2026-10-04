"""
API视图：实现资源管理接口
所有信息以 resource 目录中的实际资源为准
统一响应格式: {"code": xxx, "message": xxx, "data": data}
"""

from django.conf import settings
from django.http import FileResponse

from nassav.api_utils import build_response
from nassav.source.search_contracts import SourceSearchError, SourceSearchUnavailable


from nassav.http_base import SchemaAPIView
from nassav.http_parameters import (
    _parse_positive_int,
    _parse_bool,
    _parse_recommendation_request_params,
    _parse_recommendation_feedback_payload,
    _parse_recommendation_seed_block_payload,
    _parse_recommendation_avid_block_payload,
)


class RecommendationsDemoView(SchemaAPIView):
    """GET /api/recommendations/demo - 返回基于本地偏好的 demo 推荐结果"""

    def get(self, request):
        from nassav.recommendation import (
            RecommendationManagerError,
            recommender_manager,
        )

        try:
            execution = recommender_manager.recommend(
                request_params=_parse_recommendation_request_params(
                    request.query_params
                ),
            )
            return build_response(200, "success", execution.to_dict())
        except RecommendationManagerError as e:
            return build_response(400, str(e), None)


class RecommendationsView(SchemaAPIView):
    """GET /api/recommendations/ - 统一推荐接口"""

    def get(self, request):
        from nassav.recommendation import (
            RecommendationManagerError,
            recommender_manager,
        )

        strategy_id = request.query_params.get("strategy", "").strip() or None

        try:
            execution = recommender_manager.recommend(
                strategy_id=strategy_id,
                request_params=_parse_recommendation_request_params(
                    request.query_params
                ),
            )
            return build_response(200, "success", execution.to_dict())
        except RecommendationManagerError as e:
            return build_response(400, str(e), None)


class RecommendationOptionsView(SchemaAPIView):
    """GET /api/recommendations/options - 返回可用推荐器与策略"""

    def get(self, request):
        _ = request
        from nassav.recommendation import recommender_manager

        return build_response(200, "success", recommender_manager.get_options())


class RecommendationMetricsView(SchemaAPIView):
    """GET /api/recommendations/metrics - 返回推荐效果与状态概览"""

    def get(self, request):
        _ = request
        from nassav.recommendation.repository import recommendation_snapshot_repository

        return build_response(
            200,
            "success",
            recommendation_snapshot_repository.build_metrics(),
        )


class RecommendationFeedbackView(SchemaAPIView):
    """POST /api/recommendations/feedback - 提交推荐结果反馈"""

    def post(self, request):
        from nassav.recommendation import (
            RecommendationFeedbackError,
            recommendation_feedback_repository,
        )

        try:
            payload = _parse_recommendation_feedback_payload(request.data or {})
        except ValueError as e:
            return build_response(400, str(e), None)

        try:
            feedback_obj = recommendation_feedback_repository.record_feedback(**payload)
        except RecommendationFeedbackError as e:
            return build_response(400, str(e), None)

        return build_response(
            200,
            "success",
            {
                "snapshot_id": payload["snapshot_id"],
                "avid": payload["avid"],
                "feedback": feedback_obj.feedback if feedback_obj is not None else None,
                "feedback_value": (
                    feedback_obj.feedback_value if feedback_obj is not None else 0
                ),
            },
        )


class RecommendationSeedBlockView(SchemaAPIView):
    """POST/DELETE /api/recommendations/seed-block - 手动屏蔽或取消屏蔽 actor/genre"""

    def post(self, request):
        from nassav.models import Actor, Genre
        from nassav.recommendation.seed_profiles import (
            recommendation_seed_profile_repository,
        )

        try:
            payload = _parse_recommendation_seed_block_payload(request.data or {})
        except ValueError as e:
            return build_response(400, str(e), None)

        if payload["seed_type"] == "actor":
            try:
                actor = Actor.objects.get(pk=payload["id"])
            except Actor.DoesNotExist:
                return build_response(404, "演员不存在", None)
            profile = recommendation_seed_profile_repository.block_actor(
                actor=actor,
                reason=payload["reason"],
            )
            data = {
                "seed_type": "actor",
                "id": actor.pk,
                "name": actor.name,
                "is_blocked": profile.is_blocked,
                "block_reason": profile.block_reason,
            }
            return build_response(200, "success", data)

        try:
            genre = Genre.objects.get(pk=payload["id"])
        except Genre.DoesNotExist:
            return build_response(404, "类别不存在", None)
        except SourceSearchUnavailable as error:
            return build_response(
                503, "所选搜索源未启用或尚不支持此搜索", {"reason": str(error)}
            )
        except SourceSearchError as error:
            return build_response(
                502, "外部源搜索失败，请稍后重试", {"reason": str(error)}
            )
        except ValueError as error:
            return build_response(400, "搜索源或排序参数无效", {"reason": str(error)})
        profile = recommendation_seed_profile_repository.block_genre(
            genre=genre,
            reason=payload["reason"],
        )
        data = {
            "seed_type": "genre",
            "id": genre.pk,
            "name": genre.name,
            "is_blocked": profile.is_blocked,
            "block_reason": profile.block_reason,
        }
        return build_response(200, "success", data)

    def delete(self, request):
        from nassav.models import Actor, Genre
        from nassav.recommendation.seed_profiles import (
            recommendation_seed_profile_repository,
        )

        try:
            payload = _parse_recommendation_seed_block_payload(request.data or {})
        except ValueError as e:
            return build_response(400, str(e), None)

        if payload["seed_type"] == "actor":
            try:
                actor = Actor.objects.get(pk=payload["id"])
            except Actor.DoesNotExist:
                return build_response(404, "演员不存在", None)
            profile = recommendation_seed_profile_repository.unblock_actor(actor=actor)
            if profile is None:
                return build_response(404, "演员屏蔽记录不存在", None)
            data = {
                "seed_type": "actor",
                "id": actor.pk,
                "name": actor.name,
                "is_blocked": profile.is_blocked,
                "block_reason": profile.block_reason,
            }
            return build_response(200, "success", data)

        try:
            genre = Genre.objects.get(pk=payload["id"])
        except Genre.DoesNotExist:
            return build_response(404, "类别不存在", None)
        except SourceSearchUnavailable as error:
            return build_response(
                503, "所选搜索源未启用或尚不支持此搜索", {"reason": str(error)}
            )
        except SourceSearchError as error:
            return build_response(
                502, "外部源搜索失败，请稍后重试", {"reason": str(error)}
            )
        except ValueError as error:
            return build_response(400, "搜索源或排序参数无效", {"reason": str(error)})
        profile = recommendation_seed_profile_repository.unblock_genre(genre=genre)
        if profile is None:
            return build_response(404, "类别屏蔽记录不存在", None)
        data = {
            "seed_type": "genre",
            "id": genre.pk,
            "name": genre.name,
            "is_blocked": profile.is_blocked,
            "block_reason": profile.block_reason,
        }
        return build_response(200, "success", data)


class RecommendationAvidBlocklistView(SchemaAPIView):
    """GET/POST/DELETE /api/recommendations/avid-blocklist - 管理资源黑名单"""

    def get(self, request):
        from nassav.recommendation.avid_blocklist import (
            recommendation_avid_blocklist_repository,
        )

        page = _parse_positive_int(request.query_params.get("page"), 1)
        page_size = _parse_positive_int(request.query_params.get("page_size"), 50)
        search = str(request.query_params.get("search", "")).strip()
        data, pagination = recommendation_avid_blocklist_repository.list(
            page=page, page_size=page_size, search=search
        )
        return build_response(200, "success", data, pagination=pagination)

    def post(self, request):
        from nassav.recommendation.avid_blocklist import (
            recommendation_avid_blocklist_repository,
        )

        try:
            payload = _parse_recommendation_avid_block_payload(request.data or {})
        except ValueError as e:
            return build_response(400, str(e), None)
        data = recommendation_avid_blocklist_repository.block(**payload)
        return build_response(200, "success", data)

    def delete(self, request):
        from nassav.recommendation.avid_blocklist import (
            recommendation_avid_blocklist_repository,
        )

        try:
            payload = _parse_recommendation_avid_block_payload(request.data or {})
        except ValueError as e:
            return build_response(400, str(e), None)
        if not recommendation_avid_blocklist_repository.unblock(avid=payload["avid"]):
            return build_response(404, "资源屏蔽记录不存在", None)
        return build_response(
            200, "success", {"avid": payload["avid"], "is_blocked": False}
        )


class RecommendationResetView(SchemaAPIView):
    """POST /api/recommendations/reset - 清空推荐历史，默认保留黑名单状态"""

    def post(self, request):
        from nassav.recommendation.repository import recommendation_snapshot_repository

        preserve_blocklist = _parse_bool(
            (request.data or {}).get("preserve_blocklist")
            if hasattr(request, "data")
            else None,
            True,
        )
        result = recommendation_snapshot_repository.reset_state(
            preserve_blocklist=preserve_blocklist
        )
        return build_response(200, "success", result)


class RecommendationCoverView(SchemaAPIView):
    """GET /api/recommendations/cover - 代理并缓存推荐封面"""

    def get(self, request):
        from mimetypes import guess_type

        from django.http import HttpResponse
        from nassav.recommendation.cover_cache import RecommendationCoverCacheService
        from nassav.source import Jable

        cover_url = request.query_params.get("url", "").strip()
        if not cover_url:
            return build_response(400, "url 参数缺失", None)

        proxy = settings.PROXY_URL if settings.PROXY_ENABLED else None
        source_name = str(request.query_params.get("source", "jable")).lower()
        if source_name == "missav":
            from nassav.source.SourceManager import source_manager

            source = next(
                (
                    item
                    for _, item in source_manager.get_sources()
                    if item.get_source_name().lower() == "missav"
                ),
                None,
            )
            if source is None:
                return build_response(503, "MissAV 未启用", None)
        elif source_name == "jable":
            source = Jable(proxy=proxy)
        else:
            return build_response(400, "封面来源不受支持", None)
        service = RecommendationCoverCacheService(source)
        if not service.is_allowed_url(cover_url):
            return build_response(400, "封面来源不受支持", None)

        cover_path = service.ensure_cached(cover_url)
        if cover_path is None or not cover_path.exists():
            return HttpResponse("推荐封面获取失败", status=502)

        content_type, _ = guess_type(str(cover_path))
        return FileResponse(
            cover_path.open("rb"),
            content_type=content_type or "image/jpeg",
        )
