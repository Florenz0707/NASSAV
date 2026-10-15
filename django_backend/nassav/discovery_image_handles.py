"""Owned result references, never a client-selected upstream image capability.

Handles are not bearer authorization. Every read needs an admitted login and a
current result/account/source context; search references expire with Redis data.
"""

from dataclasses import dataclass
import hashlib
import json
from collections.abc import Callable
from django.conf import settings
from django.core import signing
from nassav.account_policy import execution_epoch
from nassav.models import RecommendationItem
from nassav.resource_reads import ReadLeaseNotFound

SALT = "nassav-owned-discovery-image-v1"


def _fingerprint(source, url, context):
    return hashlib.sha256(
        json.dumps([source, url, context], sort_keys=True).encode()
    ).hexdigest()


def _proof(value):
    return (
        isinstance(value, list)
        and len(value) == 2
        and all(isinstance(part, str) and part for part in value)
    )


def _handle(kind, user_id, epoch, reference, source, url, context):
    return signing.Signer(salt=SALT).sign_object(
        [1, kind, user_id, epoch, reference, _fingerprint(source, url, context)],
        compress=True,
    )


def recommendation_result(user_id, result):
    if not settings.SOURCE_CREDENTIALS_ENABLED or not isinstance(result, dict):
        return result
    items = result.get("items", [])
    ids = {
        item.get("snapshot_id")
        for item in items
        if isinstance(item, dict) and type(item.get("snapshot_id")) is int
    }
    rows = RecommendationItem.objects.filter(
        snapshot__owner_id=user_id, snapshot_id__in=ids
    ).select_related("snapshot")
    by_identity = {
        (row.snapshot.pk, row.avid, row.source.lower(), row.cover_url): row
        for row in rows
    }
    projected = []
    epoch = execution_epoch(user_id)
    for original in items:
        item = {key: value for key, value in original.items() if key != "cover_handle"}
        row = by_identity.get(
            (
                item.get("snapshot_id"),
                item.get("avid"),
                str(item.get("source", "")).lower(),
                item.get("cover_url"),
            )
        )
        if row and row.cover_url:
            source = row.source.lower()
            context = row.snapshot.request_payload.get("_image_contexts_v1", {}).get(
                source
            )
            if _proof(context):
                item["cover_handle"] = _handle(
                    "recommendation",
                    user_id,
                    epoch,
                    row.pk,
                    source,
                    row.cover_url,
                    context,
                )
        projected.append(item)
    return {**result, "items": projected}


def search_snapshot(user_id, snapshot):
    if not settings.SOURCE_CREDENTIALS_ENABLED or not snapshot.get("result"):
        return snapshot
    payload = snapshot["result"]
    data = payload.get("data", {})
    source = snapshot.get("query", {}).get("source")
    context = snapshot.get("query", {}).get("source_context")
    allowed = (
        user_id is not None
        and snapshot.get("owner_id") == user_id
        and snapshot.get("owner_epoch") == execution_epoch(user_id)
        and _proof(context)
    )
    projected = []
    for original in data.get("external_results", []):
        item = {key: value for key, value in original.items() if key != "cover_handle"}
        if (
            allowed
            and item.get("thumbnail_url")
            and item.get("avid")
            and str(item.get("source", source)).lower() == source
        ):
            item["cover_handle"] = _handle(
                "search",
                user_id,
                snapshot["owner_epoch"],
                [snapshot["task_id"], item["avid"]],
                source,
                item["thumbnail_url"],
                context,
            )
        projected.append(item)
    return {
        **snapshot,
        "result": {**payload, "data": {**data, "external_results": projected}},
    }


@dataclass(frozen=True)
class ImageReference:
    source: str
    url: str
    context: list
    check: Callable[[], tuple]


def resolve(user_id, token, *, search_store=None, detail_projection=None):
    from django.contrib.auth import get_user_model

    if not isinstance(token, str) or not 1 <= len(token) <= 2048:
        raise ReadLeaseNotFound("Image result unavailable")
    try:
        data = signing.Signer(salt=SALT).unsign_object(token)
    except (signing.BadSignature, ValueError, TypeError):
        raise ReadLeaseNotFound("Image result unavailable") from None
    if (
        not isinstance(data, list)
        or len(data) != 6
        or data[:1] != [1]
        or data[2] != user_id
        or not isinstance(data[1], str)
        or data[1] not in {"recommendation", "search"}
    ):
        raise ReadLeaseNotFound("Image result unavailable")
    _, kind, _, epoch, reference, digest = data
    if kind == "search" and search_store is None:
        from nassav.search_jobs import RedisSearchJobStore

        search_store = RedisSearchJobStore()

    def current():
        if (
            epoch != execution_epoch(user_id)
            or not get_user_model().objects.filter(pk=user_id, is_active=True).exists()
        ):
            raise ReadLeaseNotFound("Image account changed")
        if kind == "recommendation":
            if type(reference) is not int or reference < 1:
                raise ReadLeaseNotFound("Image result unavailable")
            row = (
                RecommendationItem.objects.filter(
                    pk=reference, snapshot__owner_id=user_id
                )
                .select_related("snapshot")
                .first()
            )
            if row is None:
                raise ReadLeaseNotFound("Image result unavailable")
            source, url = row.source.lower(), row.cover_url
            context = row.snapshot.request_payload.get("_image_contexts_v1", {}).get(
                source
            )
        else:
            from nassav.search_jobs import (
                _check_catalog_namespace,
                SearchJobAccessExpired,
            )

            if (
                not isinstance(reference, list)
                or len(reference) != 2
                or not all(isinstance(part, str) for part in reference)
            ):
                raise ReadLeaseNotFound("Image result unavailable")
            if search_store is None:
                raise ReadLeaseNotFound("Image result unavailable")
            snapshot = search_store.get(reference[0])
            if (
                not snapshot
                or snapshot.get("owner_id") != user_id
                or snapshot.get("owner_epoch") != epoch
            ):
                raise ReadLeaseNotFound("Image result unavailable")
            try:
                _check_catalog_namespace(snapshot)
            except SearchJobAccessExpired:
                raise ReadLeaseNotFound("Image result unavailable") from None
            source = snapshot.get("query", {}).get("source")
            context = snapshot.get("query", {}).get("source_context")
            rows = snapshot.get("collected_results")
            if rows is None:
                rows = (
                    (snapshot.get("result") or {})
                    .get("data", {})
                    .get("external_results", [])
                )
            row = next(
                (
                    row
                    for row in rows
                    if row.get("avid") == reference[1]
                    and str(row.get("source", source)).lower() == source
                ),
                None,
            )
            if not row:
                raise ReadLeaseNotFound("Image result unavailable")
            url = row.get("thumbnail_url")
            if not url:
                # Polling can fill a missing summary image from scoped facts.
                # Resolve the same read-only projection; never fetch a detail.
                projector = detail_projection
                if projector is None:
                    from nassav.external_search import external_search_service

                    projector = external_search_service.for_user(
                        user_id
                    ).project_existing_details
                projected, _ = projector(
                    source,
                    [row],
                    force=snapshot.get("query", {}).get("force_refresh", False),
                )
                url = projected[0].get("thumbnail_url") if projected else None
        if (
            not _proof(context)
            or not url
            or _fingerprint(source, url, context) != digest
        ):
            raise ReadLeaseNotFound("Image result changed")
        return source, url, context

    source, url, context = current()
    return ImageReference(source, url, context, current)
