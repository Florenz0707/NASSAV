"""
API视图：实现资源管理接口
所有信息以 resource 目录中的实际资源为准
统一响应格式: {"code": xxx, "message": xxx, "data": data}
"""

from nassav.api_utils import build_response
from nassav.external_search import external_search_service
from nassav.http_base import SchemaAPIView
from nassav.http_parameters import _parse_bool, _parse_positive_int
from nassav.source.search_contracts import SourceSearchError, SourceSearchUnavailable


class CatalogView(SchemaAPIView):
    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        from nassav.library_catalog import enabled
        from django.utils.cache import patch_vary_headers

        if enabled(request.user.pk):
            response["Cache-Control"] = "private, no-store"
            patch_vary_headers(response, ("Cookie",))
        return response


class ActorsListView(CatalogView):
    """GET /api/actors/ - 返回演员列表及每个演员的作品数，支持分页"""

    def get(self, request):
        from nassav.library_catalog import enabled

        if enabled(request.user.pk):
            from nassav.catalog_presentation import list_terms

            try:
                data, pagination = list_terms(
                    request.user.pk, "actor", request.query_params
                )
            except ValueError as error:
                return build_response(400, str(error), None)
            response = build_response(200, "success", data, pagination=pagination)
            response["Cache-Control"] = "private, no-store"
            response["Vary"] = "Cookie"
            return response
        from django.core.paginator import Paginator
        from django.db.models import Count, Q
        from nassav.account_models import UserAccount
        from nassav.account_policy import own_resource_ids

        from nassav.constants import ACTOR_AVATAR_PLACEHOLDER_URLS
        from nassav.models import Actor, ActorSourceMapping
        from nassav.recommendation.seed_profiles import (
            recommendation_seed_profile_repository,
        )

        # 获取参数
        page = int(request.query_params.get("page", 1))
        page_size = int(request.query_params.get("page_size", 20))
        order_by = request.query_params.get("order_by", "count")
        order = request.query_params.get("order", "desc")
        search = request.query_params.get("search", "").strip()
        actor_id = request.query_params.get("id", "").strip()

        # 构建查询
        resource_filter = (
            Q(resources__pk__in=own_resource_ids(request.user.pk))
            if UserAccount.objects.filter(user_id=request.user.pk).exists()
            else Q()
        )
        qs = Actor.objects.annotate(
            resource_count=Count("resources", filter=resource_filter)
        )

        # 过滤掉没有关联资源的演员（除非明确指定 ID）
        if not actor_id:
            qs = qs.filter(resource_count__gt=0)

        # ID 过滤（精确匹配）
        if actor_id:
            try:
                aid = int(actor_id)
                qs = qs.filter(id=aid)
            except ValueError:
                pass

        # 搜索过滤
        if search:
            qs = qs.filter(name__icontains=search)

        # 排序
        if order_by == "name":
            qs = qs.order_by("name" if order == "asc" else "-name")
        else:  # count
            if order == "desc":
                qs = qs.order_by("-resource_count", "name")
            else:
                qs = qs.order_by("resource_count", "name")

        # 分页
        paginator = Paginator(qs, page_size)
        page_obj = paginator.get_page(page)
        blocked_names = recommendation_seed_profile_repository.for_user(
            request.user.pk
        ).get_blocked_normalized_values(
            seed_type="actor",
            values=[actor.name for actor in page_obj.object_list],
        )
        actor_ids = [
            int(actor.pk) for actor in page_obj.object_list if actor.pk is not None
        ]
        mappings = {}
        for mapping in ActorSourceMapping.objects.filter(
            actor_id__in=actor_ids,
            source_name="jable",
            is_active=True,
        ):
            mapping_actor_id = getattr(mapping, "actor_id", None)
            if mapping_actor_id is None:
                continue
            mappings[int(mapping_actor_id)] = mapping
        blocked_actor_source_identifiers = (
            recommendation_seed_profile_repository.for_user(
                request.user.pk
            ).get_blocked_source_identifiers(
                seed_type="actor",
                source_name="jable",
                identifiers=[
                    str(getattr(mapping, "source_actor_slug", "") or "")
                    for mapping in mappings.values()
                ],
            )
        )

        data = [
            {
                "id": a.id,
                "name": a.name,
                "resource_count": getattr(a, "resource_count", 0),
                "avatar_url": a.avatar_url
                if a.avatar_url not in ACTOR_AVATAR_PLACEHOLDER_URLS
                else None,
                "avatar_filename": a.avatar_filename
                if a.avatar_url not in ACTOR_AVATAR_PLACEHOLDER_URLS
                else None,
                "is_blocked": (
                    recommendation_seed_profile_repository.for_user(
                        request.user.pk
                    ).normalize_value(a.name)
                    in blocked_names
                    or str(
                        getattr(mappings.get(int(a.id)), "source_actor_slug", "") or ""
                    )
                    .strip()
                    .lower()
                    in blocked_actor_source_identifiers
                ),
                "source_mapping": {
                    "source_name": mapping.source_name,
                    "source_seed_name": mapping.source_actor_name,
                    "source_seed_slug": mapping.source_actor_slug,
                    "source_seed_url": mapping.source_actor_url,
                    "aliases": list(mapping.aliases or []),
                }
                if (mapping := mappings.get(int(a.id))) is not None
                else None,
            }
            for a in page_obj.object_list
        ]

        pagination = {
            "total": paginator.count,
            "page": page_obj.number,
            "page_size": page_size,
            "pages": paginator.num_pages,
        }

        return build_response(200, "success", data, pagination=pagination)


class ActorDetailView(CatalogView):
    """GET /api/actors/<int:actor_id>/detail - 演员详情与外部源搜索结果"""

    def get(self, request, actor_id):
        from nassav.models import Actor

        source_name = str(
            request.query_params.get("source")
            or external_search_service.default_source("actor", user_id=request.user.pk)
        ).strip()
        page = _parse_positive_int(request.query_params.get("page"), 1)
        page_size = _parse_positive_int(request.query_params.get("page_size"), 20)
        ordering = str(request.query_params.get("ordering", "-views")).strip()
        force_refresh = _parse_bool(request.query_params.get("force_refresh"), False)

        try:
            result = external_search_service.search_actor_detail(
                actor_id=actor_id,
                source_name=source_name,
                page=page,
                page_size=page_size,
                ordering=ordering,
                force_refresh=force_refresh,
                user_id=request.user.pk,
            )
        except Actor.DoesNotExist:
            return build_response(404, "演员不存在", None)
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

        data = {
            "detail": result.meta.get("actor"),
            "external_source": result.meta.get("source", source_name.lower()),
            "external_meta": {
                "implemented": result.meta.get("implemented", False),
                "message": result.meta.get("message", "success"),
                "ordering": result.meta.get("ordering"),
                "fetch_pages": result.meta.get("fetch_pages"),
                "cache": result.meta.get("cache", {}),
                "supported_sources": result.meta.get("supported_sources", []),
            },
            "external_results": result.items,
        }
        return build_response(200, "success", data, pagination=result.pagination)


class GenresListView(CatalogView):
    """GET /api/genres/ - 返回类别列表及每个类别的作品数，支持分页"""

    def get(self, request):
        from nassav.library_catalog import enabled

        if enabled(request.user.pk):
            from nassav.catalog_presentation import list_terms

            try:
                data, pagination = list_terms(
                    request.user.pk, "genre", request.query_params
                )
            except ValueError as error:
                return build_response(400, str(error), None)
            response = build_response(200, "success", data, pagination=pagination)
            response["Cache-Control"] = "private, no-store"
            response["Vary"] = "Cookie"
            return response
        from django.core.paginator import Paginator
        from django.db.models import Count, Q
        from nassav.account_models import UserAccount
        from nassav.account_policy import own_resource_ids

        from nassav.models import Genre, GenreSourceMapping
        from nassav.recommendation.seed_profiles import (
            recommendation_seed_profile_repository,
        )

        # 获取参数
        page = int(request.query_params.get("page", 1))
        page_size = int(request.query_params.get("page_size", 20))
        order_by = request.query_params.get("order_by", "count")
        order = request.query_params.get("order", "desc")
        search = request.query_params.get("search", "").strip()
        genre_id = request.query_params.get("id", "").strip()

        # 构建查询
        resource_filter = (
            Q(resources__pk__in=own_resource_ids(request.user.pk))
            if UserAccount.objects.filter(user_id=request.user.pk).exists()
            else Q()
        )
        qs = Genre.objects.annotate(
            resource_count=Count("resources", filter=resource_filter)
        )

        # 过滤掉没有关联资源的类别（除非明确指定 ID）
        if not genre_id:
            qs = qs.filter(resource_count__gt=0)

        # ID 过滤（精确匹配）
        if genre_id:
            try:
                gid = int(genre_id)
                qs = qs.filter(id=gid)
            except ValueError:
                pass

        # 搜索过滤
        if search:
            qs = qs.filter(name__icontains=search)

        # 排序
        if order_by == "name":
            qs = qs.order_by("name" if order == "asc" else "-name")
        else:  # count
            if order == "desc":
                qs = qs.order_by("-resource_count", "name")
            else:
                qs = qs.order_by("resource_count", "name")

        # 分页
        paginator = Paginator(qs, page_size)
        page_obj = paginator.get_page(page)
        blocked_names = recommendation_seed_profile_repository.for_user(
            request.user.pk
        ).get_blocked_normalized_values(
            seed_type="genre",
            values=[genre.name for genre in page_obj.object_list],
        )
        genre_ids = [
            int(genre.pk) for genre in page_obj.object_list if genre.pk is not None
        ]
        mappings = {}
        for mapping in GenreSourceMapping.objects.filter(
            genre_id__in=genre_ids,
            source_name="jable",
            is_active=True,
        ):
            mapping_genre_id = getattr(mapping, "genre_id", None)
            if mapping_genre_id is None:
                continue
            mappings[int(mapping_genre_id)] = mapping
        blocked_genre_source_identifiers = (
            recommendation_seed_profile_repository.for_user(
                request.user.pk
            ).get_blocked_source_identifiers(
                seed_type="genre",
                source_name="jable",
                identifiers=[
                    str(getattr(mapping, "source_genre_slug", "") or "")
                    for mapping in mappings.values()
                ],
            )
        )

        data = [
            {
                "id": g.id,
                "name": g.name,
                "resource_count": getattr(g, "resource_count", 0),
                "is_blocked": (
                    recommendation_seed_profile_repository.for_user(
                        request.user.pk
                    ).normalize_value(g.name)
                    in blocked_names
                    or str(
                        getattr(mappings.get(int(g.id)), "source_genre_slug", "") or ""
                    )
                    .strip()
                    .lower()
                    in blocked_genre_source_identifiers
                ),
                "source_mapping": {
                    "source_name": mapping.source_name,
                    "source_seed_name": mapping.source_genre_name,
                    "source_seed_slug": mapping.source_genre_slug,
                    "source_seed_url": mapping.source_genre_url,
                    "aliases": list(mapping.aliases or []),
                }
                if (mapping := mappings.get(int(g.id))) is not None
                else None,
            }
            for g in page_obj.object_list
        ]

        pagination = {
            "total": paginator.count,
            "page": page_obj.number,
            "page_size": page_size,
            "pages": paginator.num_pages,
        }

        return build_response(200, "success", data, pagination=pagination)


class GenreDetailView(CatalogView):
    """GET /api/genres/<int:genre_id>/detail - 类别详情与外部源搜索结果"""

    def get(self, request, genre_id):
        from nassav.models import Genre

        source_name = str(
            request.query_params.get("source")
            or external_search_service.default_source("genre", user_id=request.user.pk)
        ).strip()
        page = _parse_positive_int(request.query_params.get("page"), 1)
        page_size = _parse_positive_int(request.query_params.get("page_size"), 20)
        ordering = str(request.query_params.get("ordering", "-views")).strip()
        force_refresh = _parse_bool(request.query_params.get("force_refresh"), False)

        try:
            result = external_search_service.search_genre_detail(
                genre_id=genre_id,
                source_name=source_name,
                page=page,
                page_size=page_size,
                ordering=ordering,
                force_refresh=force_refresh,
                user_id=request.user.pk,
            )
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

        data = {
            "detail": result.meta.get("genre"),
            "external_source": result.meta.get("source", source_name.lower()),
            "external_meta": {
                "implemented": result.meta.get("implemented", False),
                "message": result.meta.get("message", "success"),
                "ordering": result.meta.get("ordering"),
                "fetch_pages": result.meta.get("fetch_pages"),
                "cache": result.meta.get("cache", {}),
                "supported_sources": result.meta.get("supported_sources", []),
            },
            "external_results": result.items,
        }
        return build_response(200, "success", data, pagination=result.pagination)
