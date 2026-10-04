"""
API视图：实现资源管理接口
所有信息以 resource 目录中的实际资源为准
统一响应格式: {"code": xxx, "message": xxx, "data": data}
"""

from loguru import logger

from nassav.api_utils import build_response
from nassav.legacy_batch import legacy_add_operation, legacy_refresh_operation
from nassav.resource_deletion import (
    InvalidResourceIdentifier,
    ResourceDeletionFailure,
    resource_deletion_service,
)
from nassav.serializers import (
    NewResourceSerializer,
)
from nassav.services import list_resources, source_manager


from nassav.http_base import SchemaAPIView
from nassav.resource_presentation import (
    serialize_legacy_resource as _serialize_resource_obj,
)


class ResourcesListView(SchemaAPIView):
    """GET /api/resources/ - consolidated resource listing with filters/pagination"""

    def get(self, request):
        # support legacy sort_by / order params from older endpoints
        params = request.query_params.copy()
        sort_by = params.get("sort_by")
        order = params.get("order", "desc")
        if sort_by:
            sort_map = {
                "avid": "avid",
                "metadata_create_time": "metadata_created_at",
                "metadata_update_time": "metadata_updated_at",
                "video_create_time": "video_saved_at",
                "source": "source",
            }
            sort_field = sort_map.get(sort_by, None)
            if sort_field:
                if order == "desc":
                    params["ordering"] = f"-{sort_field}"
                else:
                    params["ordering"] = sort_field

        objs, pagination = list_resources(params)
        # reuse ResourceSummarySerializer
        from nassav.serializers import ResourceSummarySerializer

        serializer = ResourceSummarySerializer(objs, many=True)

        # return standardized envelope with pagination field
        return build_response(200, "success", serializer.data, pagination=pagination)


class ResourceView(SchemaAPIView):
    """
    POST /api/resource/new
    通过avid获取资源信息并保存（HTML、封面、元数据）

    请求参数:
        avid: 视频编号
        downloader: 指定源名称，默认 "any" 表示尝试所有源
    """

    def post(self, request):
        from nassav.resource_service import (
            ResourceAccessDeniedError,
            ResourceAlreadyExistsError,
            ResourceFetchError,
            ResourceNotFoundError,
            resource_service,
        )

        serializer = NewResourceSerializer(data=request.data)
        if not serializer.is_valid():
            return build_response(400, "参数错误", serializer.errors)

        avid = serializer.validated_data["avid"].upper()
        source = serializer.validated_data.get("source", "any").lower()

        # 检查指定源是否存在
        if source != "any":
            available_sources = [
                name.lower() for name, _ in source_manager.get_sources()
            ]
            if source not in available_sources:
                return build_response(
                    400,
                    f"源 {source} 不存在",
                    {
                        "available_sources": [
                            name for name, _ in source_manager.get_sources()
                        ]
                    },
                )

        # 调用ResourceService添加资源
        try:
            result = resource_service.add_resource(avid, source)

            # 记录封面下载失败警告
            if not result["cover_saved"]:
                logger.warning(f"封面下载失败: {avid}")

            # 只返回指定的字段
            resource_data = result["resource"]
            filtered_resource = {
                "avid": resource_data.get("avid"),
                "original_title": resource_data.get("original_title"),
                "source_title": resource_data.get("source_title"),
                "translated_title": resource_data.get("translated_title"),
                "source": resource_data.get("source"),
            }

            return build_response(
                201,
                "success",
                {
                    "resource": filtered_resource,
                    "cover_downloaded": result["cover_saved"],
                    "metadata_saved": result["metadata_saved"],
                    "scraped": result["scraped"],
                },
            )

        except ResourceAlreadyExistsError as e:
            # 409 Conflict - 资源已存在
            # 只返回指定的字段
            filtered_resource = {
                "avid": e.resource_data.get("avid"),
                "original_title": e.resource_data.get("original_title"),
                "source_title": e.resource_data.get("source_title"),
                "translated_title": e.resource_data.get("translated_title"),
                "source": e.resource_data.get("source"),
            }
            return build_response(409, str(e), filtered_resource)

        except ResourceNotFoundError as e:
            # 404 Not Found - 所有源都返回404
            return build_response(404, str(e), None)

        except ResourceAccessDeniedError as e:
            # 403 Forbidden - 有源返回403
            return build_response(403, str(e), None)

        except ResourceFetchError as e:
            # 502 Bad Gateway - 网络错误
            return build_response(502, str(e), None)

        except Exception as e:
            # 500 Internal Server Error - 未预期的错误
            logger.error(f"添加资源失败: {avid}, 错误: {e}", exc_info=True)
            return build_response(500, f"服务器内部错误: {str(e)}", None)


class RefreshResourceView(SchemaAPIView):
    """
    POST /api/resource/refresh/{avid}
    刷新已有资源的元数据和m3u8链接，使用原有source获取

    支持细粒度刷新参数：
    - refresh_m3u8: 是否刷新 m3u8 链接（默认 true）
    - refresh_metadata: 是否刷新元数据（默认 true）
    - retranslate: 是否重新翻译标题（默认 false）

    注意：当同时刷新元数据和重新翻译时，会先刷新元数据获取新标题，再执行翻译
    """

    def post(self, request, avid):
        from nassav.resource_service import (
            ResourceNotFoundError,
            resource_service,
        )

        avid = avid.upper()

        # 解析参数，默认全部刷新
        refresh_m3u8 = request.data.get("refresh_m3u8", True)
        refresh_metadata = request.data.get("refresh_metadata", True)
        retranslate = request.data.get("retranslate", False)

        result_info = {}

        # 刷新元数据和/或 m3u8
        if refresh_metadata or refresh_m3u8:
            try:
                # 使用ResourceService刷新资源
                refresh_result = resource_service.refresh_resource(
                    avid, scrape=refresh_metadata, download_cover=refresh_metadata
                )

                result_info["cover_downloaded"] = refresh_result["cover_saved"]
                result_info["metadata_saved"] = refresh_result["metadata_saved"]
                result_info["scraped"] = refresh_result.get("scraped", False)
                result_info["metadata_refreshed"] = refresh_metadata
                result_info["m3u8_refreshed"] = refresh_m3u8
                result_info["m3u8_updated"] = refresh_result.get("m3u8_updated", False)

            except ResourceNotFoundError as e:
                # 资源不存在于数据库中
                return build_response(404, str(e), None)

            except Exception as e:
                # 其他错误
                logger.error(f"刷新资源失败: {avid}, 错误: {e}", exc_info=True)
                return build_response(500, f"刷新失败: {str(e)}", None)

        # 重新翻译（必须在元数据刷新之后执行，确保使用最新的标题）
        if retranslate:
            try:
                from nassav.composition import build_translation_requests
                from nassav.translation_requests import TranslationResourceMissing

                try:
                    build_translation_requests().request(avid)
                except TranslationResourceMissing:
                    return build_response(404, f"{avid} 的资源不存在", None)
                result_info["translation_queued"] = True
                logger.info(f"已提交 {avid} 的翻译任务")
            except Exception as e:
                logger.error(f"提交翻译任务失败: {e}")
                result_info["translation_error"] = str(e)

        # 返回刷新后的资源对象，便于前端局部刷新
        try:
            from nassav.models import AVResource

            resource = AVResource.objects.filter(avid=avid).first()
            if resource:
                resource.refresh_from_db()
                resource_data = _serialize_resource_obj(resource)
            else:
                resource_data = None
        except Exception as e:
            logger.error(f"序列化资源对象失败: {e}")
            resource_data = None

        result_info["resource"] = resource_data
        return build_response(200, "success", result_info)


class DeleteResourceView(SchemaAPIView):
    """
    DELETE /api/resource/{avid}
    删除整个资源目录（包括 HTML、封面、元数据、视频）
    """

    def delete(self, request, avid):
        _ = request
        try:
            result = resource_deletion_service.delete_resource(
                avid, serialize=_serialize_resource_obj
            )
        except InvalidResourceIdentifier:
            return build_response(400, "avid 无效", None)
        except ResourceDeletionFailure as exc:
            return build_response(
                500,
                "删除未完成，请重试",
                {
                    "avid": avid.upper(),
                    "deleted_files": list(exc.deleted_files),
                    "failed_stage": exc.stage,
                    "retryable": True,
                },
            )
        if not result.found:
            return build_response(404, f"资源 {avid.upper()} 不存在", None)
        return build_response(
            200,
            "success",
            {
                "resource": result.resource,
                "avid": avid.upper(),
                "deleted_files": list(result.deleted_files),
            },
        )


class ResourcesBatchView(SchemaAPIView):
    """POST /api/resources/batch

    Body example:
      { "actions": [ {"action":"add","avid":"ABC-123","source":"any"},
                      {"action":"delete-video","avid":"XYZ-001"},
                      {"action":"delete-all","avid":"OLD-999"},
                      {"action":"refresh","avid":"DEF-222"} ] }

    支持的 action 类型：
    - add: 添加资源
    - refresh: 刷新资源元数据和 m3u8
    - delete-video: 只删除视频文件，保留元数据
    - delete-all 或 delete: 删除全部数据（视频+元数据+封面+备份）
    """

    def post(self, request):
        data = request.data or {}
        actions = data.get("actions") or []
        results = []

        for act in actions:
            if not isinstance(act, dict):
                results.append(
                    {
                        "action": None,
                        "avid": None,
                        "code": 400,
                        "message": "操作无效",
                        "resource": None,
                    }
                )
                continue
            raw_action = act.get("action")
            raw_avid = act.get("avid")
            action = raw_action.lower() if isinstance(raw_action, str) else ""
            avid = raw_avid.upper() if isinstance(raw_avid, str) else ""
            if not avid:
                results.append(
                    {
                        "action": action,
                        "avid": None,
                        "code": 400,
                        "message": "avid 缺失",
                        "resource": None,
                    }
                )
                continue

            try:
                if action == "add":
                    results.append(
                        legacy_add_operation.execute(avid, act, _serialize_resource_obj)
                    )

                elif action == "delete-video":
                    try:
                        deletion = resource_deletion_service.delete_video(avid)
                    except InvalidResourceIdentifier:
                        results.append(
                            {
                                "action": action,
                                "avid": avid,
                                "code": 400,
                                "message": "avid 无效",
                                "resource": None,
                            }
                        )
                        continue
                    except ResourceDeletionFailure as exc:
                        results.append(
                            {
                                "action": action,
                                "avid": avid,
                                "code": 500,
                                "message": "删除未完成，请重试",
                                "resource": None,
                                "failed_stage": exc.stage,
                                "retryable": True,
                                "deleted_files": list(exc.deleted_files),
                            }
                        )
                        continue
                    if not deletion.found:
                        results.append(
                            {
                                "action": action,
                                "avid": avid,
                                "code": 404,
                                "message": "视频不存在",
                                "resource": None,
                            }
                        )
                        continue
                    results.append(
                        {
                            "action": action,
                            "avid": avid,
                            "code": 200,
                            "message": "视频已删除",
                            "deleted_file": deletion.deleted_files[0]
                            if deletion.deleted_files
                            else None,
                            "file_size": deletion.file_size,
                        }
                    )

                elif action in ["delete", "delete-all"]:
                    try:
                        deletion = resource_deletion_service.delete_resource(
                            avid, serialize=_serialize_resource_obj
                        )
                    except InvalidResourceIdentifier:
                        results.append(
                            {
                                "action": action,
                                "avid": avid,
                                "code": 400,
                                "message": "avid 无效",
                                "resource": None,
                            }
                        )
                        continue
                    except ResourceDeletionFailure as exc:
                        results.append(
                            {
                                "action": action,
                                "avid": avid,
                                "code": 500,
                                "message": "删除未完成，请重试",
                                "resource": None,
                                "failed_stage": exc.stage,
                                "retryable": True,
                                "deleted_files": list(exc.deleted_files),
                            }
                        )
                        continue
                    if not deletion.found:
                        results.append(
                            {
                                "action": action,
                                "avid": avid,
                                "code": 404,
                                "message": "资源不存在",
                                "resource": None,
                            }
                        )
                        continue
                    results.append(
                        {
                            "action": action,
                            "avid": avid,
                            "code": 200,
                            "message": "已删除全部数据",
                            "resource": deletion.resource,
                            "deleted_files": list(deletion.deleted_files),
                        }
                    )

                elif action == "refresh":
                    results.append(
                        legacy_refresh_operation.execute(
                            avid, act, _serialize_resource_obj
                        )
                    )

                else:
                    results.append(
                        {
                            "action": action,
                            "avid": avid,
                            "code": 400,
                            "message": "未知 action",
                            "resource": None,
                        }
                    )

            except Exception as e:
                logger.exception(f"批量操作失败: {e}")
                results.append(
                    {
                        "action": action,
                        "avid": avid,
                        "code": 500,
                        "message": str(e),
                        "resource": None,
                    }
                )

        return build_response(200, "success", {"results": results})


class ResourceStatusView(SchemaAPIView):
    """
    PATCH /api/resource/{avid}/status
    更新资源的观看状态和收藏状态

    请求参数:
        watched: 是否已观看 (boolean, optional)
        is_favorite: 是否收藏 (boolean, optional)
    """

    def patch(self, request, avid):
        avid = avid.upper()

        try:
            from nassav.models import AVResource

            resource = AVResource.objects.filter(avid=avid).first()
            if not resource:
                return build_response(404, f"资源 {avid} 不存在", None)

            data = request.data or {}
            updated_fields = []

            # 更新 watched 字段
            if "watched" in data:
                watched = data.get("watched")
                if not isinstance(watched, bool):
                    return build_response(400, "watched 参数必须是布尔值", None)
                resource.watched = watched
                updated_fields.append("watched")

            # 更新 is_favorite 字段
            if "is_favorite" in data:
                is_favorite = data.get("is_favorite")
                if not isinstance(is_favorite, bool):
                    return build_response(400, "is_favorite 参数必须是布尔值", None)
                resource.is_favorite = is_favorite
                updated_fields.append("is_favorite")

            if not updated_fields:
                return build_response(400, "未提供任何要更新的字段", None)

            resource.save(update_fields=updated_fields)

            return build_response(
                200,
                "success",
                {
                    "avid": avid,
                    "watched": resource.watched,
                    "is_favorite": resource.is_favorite,
                },
            )
        except Exception as e:
            logger.error(f"更新资源状态失败: {e}")
            return build_response(500, f"更新失败: {str(e)}", None)


class ResourceJobView(SchemaAPIView):
    """Submit one scrape job without waiting for browser or metadata requests."""

    def post(self, request):
        from nassav.scrape_jobs import job_token, submit_resource_job
        from nassav.resource_service import (
            ResourceAlreadyExistsError,
            ResourceNotFoundError,
        )
        from nassav.serializers import ResourceJobSerializer

        serializer = ResourceJobSerializer(data=request.data)
        if not serializer.is_valid():
            return build_response(400, "参数错误", serializer.errors)
        item = serializer.validated_data
        action = item["action"]
        source = item.get("source", "any").lower()
        if action == "add" and source != "any":
            if source not in {name.lower() for name, _ in source_manager.get_sources()}:
                return build_response(400, "源不存在", {"source": source})
        options = {
            name: item[name]
            for name in ("refresh_m3u8", "refresh_metadata", "retranslate")
        }
        try:
            snapshot, duplicate = submit_resource_job(
                action, item["avid"], source, options
            )
        except ResourceAlreadyExistsError:
            return build_response(409, "资源已存在", None)
        except ResourceNotFoundError:
            return build_response(404, "资源不存在", None)
        except ValueError as exc:
            return build_response(400, str(exc), None)
        except Exception:
            logger.exception("提交资源任务失败")
            return build_response(503, "任务队列暂不可用", None)
        data = {
            "task_id": snapshot["task_id"],
            "status_url": f"/nassav/api/resource/jobs/{snapshot['task_id']}",
            "status_token": job_token(snapshot["task_id"]),
            "job": snapshot,
            "duplicate": duplicate,
        }
        return build_response(202, "任务已受理", data)


class ResourceJobStatusView(SchemaAPIView):
    """Return the latest Redis snapshot, including a terminal result when present."""

    def get(self, request, task_id):
        from nassav.scrape_jobs import get_resource_job, valid_job_token

        if not valid_job_token(
            str(task_id), request.headers.get("X-Resource-Job-Token", "")
        ):
            return build_response(403, "无权查询此任务", None)
        try:
            snapshot = get_resource_job(str(task_id))
        except Exception:
            logger.exception("查询资源任务失败")
            return build_response(503, "任务状态暂不可用", None)
        if snapshot is None:
            return build_response(404, "任务不存在或已过期", None)
        return build_response(200, "success", snapshot)


class ResourceJobBatchView(SchemaAPIView):
    """Submit independent add/refresh jobs and report each outcome."""

    def post(self, request):
        from nassav.resource_service import (
            ResourceAlreadyExistsError,
            ResourceNotFoundError,
        )
        from nassav.scrape_jobs import job_token, submit_resource_job
        from nassav.serializers import ResourceJobSerializer

        actions = (
            request.data.get("actions") if isinstance(request.data, dict) else None
        )
        if not isinstance(actions, list) or not 1 <= len(actions) <= 100:
            return build_response(400, "actions 必须包含 1 至 100 项", None)
        results = []
        for raw_item in actions:
            serializer = ResourceJobSerializer(data=raw_item)
            if not serializer.is_valid():
                results.append(
                    {
                        "avid": raw_item.get("avid")
                        if isinstance(raw_item, dict)
                        else None,
                        "action": raw_item.get("action")
                        if isinstance(raw_item, dict)
                        else None,
                        "code": 400,
                        "message": "参数错误",
                        "errors": serializer.errors,
                    }
                )
                continue
            item = serializer.validated_data
            action = item["action"]
            avid = item["avid"].upper()
            source = item.get("source", "any").lower()
            if action == "add" and source != "any":
                if source not in {
                    name.lower() for name, _ in source_manager.get_sources()
                }:
                    results.append(
                        {
                            "avid": avid,
                            "action": action,
                            "code": 400,
                            "message": "源不存在",
                        }
                    )
                    continue
            options = {
                name: item[name]
                for name in ("refresh_m3u8", "refresh_metadata", "retranslate")
            }
            try:
                snapshot, duplicate = submit_resource_job(action, avid, source, options)
                results.append(
                    {
                        "avid": avid,
                        "action": action,
                        "code": 202,
                        "task_id": snapshot["task_id"],
                        "status_url": f"/nassav/api/resource/jobs/{snapshot['task_id']}",
                        "status_token": job_token(snapshot["task_id"]),
                        "duplicate": duplicate,
                    }
                )
            except ResourceAlreadyExistsError:
                results.append(
                    {
                        "avid": avid,
                        "action": action,
                        "code": 409,
                        "message": "资源已存在",
                    }
                )
            except ResourceNotFoundError:
                results.append(
                    {
                        "avid": avid,
                        "action": action,
                        "code": 404,
                        "message": "资源不存在",
                    }
                )
            except Exception:
                logger.exception("批量提交资源任务失败: {}", avid)
                results.append(
                    {
                        "avid": avid,
                        "action": action,
                        "code": 503,
                        "message": "任务队列暂不可用",
                    }
                )
        return build_response(202, "批量提交完成", {"results": results})
