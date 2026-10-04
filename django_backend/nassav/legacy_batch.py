"""Synchronous compatibility operations for the legacy resources/batch API."""

from abc import ABC, abstractmethod
from typing import Callable

from loguru import logger

from nassav.models import AVResource
from nassav.resource_adapters import ResourceReader, DjangoResourceReader
from nassav.resource_contracts import ResourceWorkflow
from nassav.resource_service import (
    ResourceAccessDeniedError,
    ResourceAlreadyExistsError,
    ResourceFetchError,
    ResourceNotFoundError,
    resource_service,
)


class LegacyBatchOperation(ABC):
    """One synchronous batch item with the established per-item envelope."""

    def __init__(
        self,
        *,
        reader: ResourceReader | None = None,
        workflow: ResourceWorkflow | None = None,
    ):
        self.reader = reader if reader is not None else DjangoResourceReader()
        self.workflow = workflow if workflow is not None else resource_service

    @abstractmethod
    def execute(
        self, avid: str, options: dict, serialize: Callable[[AVResource], dict]
    ) -> dict: ...


class AddBatchOperation(LegacyBatchOperation):
    def execute(
        self, avid: str, options: dict, serialize: Callable[[AVResource], dict]
    ) -> dict:
        existing = self.reader.get(avid)
        if existing:
            return dict(
                action="add",
                avid=avid,
                code=200,
                message="already exists",
                resource=serialize(existing),
            )
        source = (options.get("source") or "any").lower()
        # The former unconditional two-second wait had no source rate evidence.
        # Source adapters own retries and target-specific pacing.
        try:
            result = self.workflow.add_resource(avid, source)
            return dict(
                action="add",
                avid=avid,
                code=201,
                message="created",
                resource=result["resource"],
            )
        except ResourceAlreadyExistsError as exc:
            return dict(
                action="add",
                avid=avid,
                code=200,
                message="already exists",
                resource=exc.resource_data,
            )
        except ResourceNotFoundError as exc:
            return self._error(avid, 404, str(exc))
        except ResourceAccessDeniedError as exc:
            return self._error(avid, 403, str(exc))
        except ResourceFetchError as exc:
            return self._error(avid, 502, str(exc))
        except Exception as exc:
            logger.exception("Legacy batch add failed for {}", avid)
            return self._error(avid, 500, f"服务器内部错误: {exc}")

    @staticmethod
    def _error(avid: str, code: int, message: str) -> dict:
        return dict(action="add", avid=avid, code=code, message=message, resource=None)


class RefreshBatchOperation(LegacyBatchOperation):
    def execute(
        self, avid: str, options: dict, serialize: Callable[[AVResource], dict]
    ) -> dict:
        resource = self.reader.get(avid)
        if not resource:
            return self._error(avid, 404, "资源不存在")
        if not resource.source:
            return self._error(avid, 400, "没有 source 信息")
        refresh_m3u8 = options.get("refresh_m3u8", True)
        refresh_metadata = options.get("refresh_metadata", True)
        retranslate = options.get("retranslate", False)
        details = {}
        if refresh_metadata or refresh_m3u8:
            try:
                refreshed = self.workflow.refresh_resource(
                    avid, scrape=refresh_metadata, download_cover=refresh_metadata
                )
                details.update(
                    metadata_refreshed=refresh_metadata,
                    m3u8_refreshed=refresh_m3u8,
                    cover_saved=refreshed["cover_saved"],
                    metadata_saved=refreshed["metadata_saved"],
                    scraped=refreshed.get("scraped", False),
                )
            except ResourceNotFoundError as exc:
                return self._error(avid, 404, str(exc))
            except Exception as exc:
                logger.exception("Legacy batch refresh failed for {}", avid)
                return self._error(avid, 500, f"刷新失败: {exc}")
        if retranslate:
            try:
                from nassav.composition import build_translation_requests

                build_translation_requests().request(avid)
                details["translation_queued"] = True
            except Exception as exc:
                logger.exception("Legacy batch translation submit failed for {}", avid)
                details["translation_error"] = str(exc)
        resource.refresh_from_db()
        return dict(
            action="refresh",
            avid=avid,
            code=200,
            message="refreshed",
            resource=serialize(resource),
            **details,
        )

    @staticmethod
    def _error(avid: str, code: int, message: str) -> dict:
        return dict(
            action="refresh", avid=avid, code=code, message=message, resource=None
        )


legacy_add_operation = AddBatchOperation()
legacy_refresh_operation = RefreshBatchOperation()
