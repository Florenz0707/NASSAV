"""Freeze URL/OpenAPI and media response contracts across HTTP module moves."""

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.urls import URLPattern, URLResolver, get_resolver
from drf_spectacular.generators import SchemaGenerator
from nassav.resource_media import FileCoverLocator
from nassav.translation_requests import DjangoTranslationRequests


def routes(patterns, prefix=""):
    result = []
    for pattern in patterns:
        route = prefix + str(pattern.pattern)
        if isinstance(pattern, URLResolver):
            result.extend(routes(pattern.url_patterns, route))
        elif isinstance(pattern, URLPattern) and "nassav" in route:
            result.append(
                [
                    route,
                    pattern.name,
                    getattr(
                        getattr(pattern.callback, "view_class", None),
                        "__name__",
                        pattern.callback.__name__,
                    ),
                ]
            )
    return result


def test_url_and_openapi_contract_remains_identical():
    baseline = json.loads(
        (Path(__file__).parent / "fixtures/backend_http_contract.json").read_text()
    )
    schema = SchemaGenerator().get_schema(request=None, public=True)
    recommendation_routes = [
        [
            "nassav/api/recommendations/jobs",
            "recommendation-job-submit",
            "RecommendationJobSubmitView",
        ],
        [
            "nassav/api/recommendations/jobs/<uuid:job_id>",
            "recommendation-job-status",
            "RecommendationJobStatusView",
        ],
        [
            "nassav/api/recommendations/jobs/<uuid:job_id>/cancel",
            "recommendation-job-cancel",
            "RecommendationJobCancelView",
        ],
    ]
    control_routes = [
        ["nassav/api/tasks/jobs", "task-job-list", "TaskJobListView"],
        [
            "nassav/api/tasks/jobs/actions",
            "task-job-batch-control",
            "TaskBatchControlView",
        ],
        [
            "nassav/api/tasks/jobs/<uuid:job_id>/cleanup/retry",
            "task-job-cleanup-retry",
            "TaskCleanupRetryView",
        ],
        ["nassav/api/tasks/jobs/<uuid:job_id>", "task-job-status", "TaskJobStatusView"],
        [
            "nassav/api/tasks/jobs/<uuid:job_id>/<str:action>",
            "task-job-control",
            "TaskControlView",
        ],
    ]
    # Authorized additions are explicit; the legacy snapshot is not regenerated.
    assert routes(get_resolver().url_patterns) == [
        *recommendation_routes,
        *control_routes,
        *baseline["routes"],
    ]
    control_paths = {
        "/nassav/api/recommendations/jobs": {"post"},
        "/nassav/api/recommendations/jobs/{job_id}": {"get"},
        "/nassav/api/recommendations/jobs/{job_id}/cancel": {"post"},
        "/nassav/api/tasks/jobs": {"get"},
        "/nassav/api/tasks/jobs/actions": {"post"},
        "/nassav/api/tasks/jobs/{job_id}": {"get"},
        "/nassav/api/tasks/jobs/{job_id}/{action}": {"post"},
        "/nassav/api/tasks/jobs/{job_id}/cleanup/retry": {"post"},
    }
    assert {path: set(schema["paths"][path]) for path in control_paths} == control_paths
    assert {
        path: value
        for path, value in schema["paths"].items()
        if path not in control_paths
    } == baseline["paths"]
    added_schemas = {
        "ActorPreferenceEnum",
        "GenrePreferenceEnum",
        "RecommendationQuery",
        "StrategyEnum",
        "TypePreferenceEnum",
    }
    components = schema.get("components", {})
    assert (
        set(components["schemas"]) - set(baseline["components"]["schemas"])
        == added_schemas
    )
    assert {
        **components,
        "schemas": {
            key: value
            for key, value in components["schemas"].items()
            if key not in added_schemas
        },
    } == baseline["components"]


@pytest.mark.django_db(transaction=True)
def test_cover_original_fresh_thumbnail_and_fallback_headers(
    api_client, settings, tmp_path
):
    covers, thumbs = tmp_path / "covers", tmp_path / "thumbs"
    covers.mkdir()
    original = covers / "HTTP-001.jpg"
    original.write_bytes(b"original")
    os.utime(original, (1, 1))
    settings.COVER_DIR, settings.THUMBNAIL_DIR = covers, thumbs
    response = api_client.get("/nassav/api/resource/cover", {"avid": "HTTP-001"})
    assert (
        response.status_code == 200
        and response["Cache-Control"] == "public, max-age=31536000"
    )
    etag = response["ETag"]
    response.close()
    conditional = api_client.get(
        "/nassav/api/resource/cover", {"avid": "HTTP-001"}, HTTP_IF_NONE_MATCH=etag
    )
    assert conditional.status_code == 304 and conditional["ETag"] == etag
    assert "Last-Modified" in conditional
    fallback = api_client.get(
        "/nassav/api/resource/cover", {"avid": "HTTP-001", "size": "small"}
    )
    assert fallback.status_code == 200 and "ETag" not in fallback
    assert b"".join(fallback.streaming_content) == b"original"
    fallback.close()
    thumbnail = thumbs / "small/HTTP-001.jpg"
    thumbnail.parent.mkdir(parents=True, exist_ok=True)
    thumbnail.write_bytes(b"thumbnail")
    os.utime(thumbnail, (2, 2))
    fresh = api_client.get(
        "/nassav/api/resource/cover", {"avid": "HTTP-001", "size": "small"}
    )
    assert fresh.status_code == 200 and "ETag" in fresh
    fresh.close()
    assert (
        api_client.get(
            "/nassav/api/resource/cover", {"avid": "HTTP-001", "size": "invalid"}
        ).status_code
        == 400
    )
    assert (
        api_client.get(
            "/nassav/api/resource/cover", {"avid": "MISSING", "size": "invalid"}
        ).status_code
        == 404
    )


def test_new_thumbnail_has_same_header_contract_and_can_be_replaced(tmp_path):
    cover = tmp_path / "HTTP-002.jpg"
    cover.write_bytes(b"original")

    def thumbnailer(source, target, width):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"thumb")
        return True

    locator = FileCoverLocator(
        tmp_path, tmp_path / "thumbs", thumbnailer, lambda path: '"etag"'
    )
    generated = locator.locate("HTTP-002", "small")
    assert generated.content_type == "image/jpeg" and generated.etag is None
    fresh = locator.locate("HTTP-002", "small")
    assert fresh.etag == '"etag"'


@pytest.mark.django_db
def test_retranslation_reset_precedes_dispatch_and_preserves_submission_failure(
    resource_factory,
):
    resource = resource_factory(
        avid="HTTP-003", translated_title="old", translation_status="completed"
    )
    observed = []

    def dispatch(avid, generation):
        resource.refresh_from_db()
        observed.append((avid, resource.translation_status, resource.translated_title))
        raise RuntimeError("queue unavailable")

    with pytest.raises(RuntimeError, match="queue unavailable"):
        DjangoTranslationRequests(dispatch).request(resource.avid)
    assert observed == [(resource.avid, "pending", None)]


@pytest.mark.django_db
def test_refresh_retranslation_uses_shared_dispatch(
    api_client, resource_factory, monkeypatch
):
    from nassav.tasks import translate_title_task

    resource = resource_factory(
        avid="HTTP-004", translated_title="old", translation_status="completed"
    )
    submitted = []
    monkeypatch.setattr(
        translate_title_task,
        "delay",
        lambda avid, **kwargs: (
            submitted.append(avid) or SimpleNamespace(id="translation")
        ),
    )
    response = api_client.post(
        f"/nassav/api/resource/refresh/{resource.avid}",
        {
            "avid": resource.avid,
            "refresh_m3u8": False,
            "refresh_metadata": False,
            "retranslate": True,
        },
        format="json",
    )
    assert response.status_code == 200 and submitted == [resource.avid]
    resource.refresh_from_db()
    assert (
        resource.translation_status == "pending" and resource.translated_title is None
    )
