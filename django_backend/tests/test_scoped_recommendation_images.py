"""Real encrypted identities and files; synthetic image transport only."""

from contextlib import contextmanager
from unittest.mock import Mock

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from nassav.credential_crypto import CredentialUnavailable
from nassav.recommendation.cover_cache import RecommendationCoverCacheService
from nassav.recommendation.images import RecommendationImages, source_image_context
from nassav.recommendation_image_files import open_cache_image
from nassav.resource_reads import ReadLeaseNotFound
from nassav.source.Jable import Jable
from test_scoped_source_runtime import runtime as runtime, context

pytestmark = pytest.mark.django_db
URL = "https://assets-cdn.jable.tv/abc/cover.jpg"


@pytest.fixture
def images(runtime, settings, tmp_path, monkeypatch):
    users, records = runtime
    settings.RECOMMENDATION_COVER_DIR = tmp_path
    responses = []

    def fetch(url, **kwargs):
        response = Mock(status_code=200, headers={"Content-Type": "image/jpeg"})
        response.iter_content.return_value = iter([f"image-{len(responses)}".encode()])
        responses.append((response, kwargs))
        return response

    monkeypatch.setattr("nassav.recommendation.cover_cache.requests.get", fetch)
    sources = []

    @contextmanager
    def scope(actor, name, check_result):
        from nassav.task_network import TaskNetworkControl

        source = Jable("http://global-proxy.test:8080")
        source.set_task_control(TaskNetworkControl(check_result))
        source.bind_credential_context(context(records, actor))
        source.load_cookie_from_db()
        sources.append(source)
        yield source
        source.credential_context.check()

    checks = Mock()
    service = RecommendationImages(
        scope, checks, lambda path: open_cache_image(tmp_path, path)
    )
    return users, records, service, sources, responses


def test_same_url_different_credentials_do_not_share_cache_and_no_cdn_cookie(images):
    users, _, service, sources, responses = images
    for index, user in enumerate(users):
        image = service.open(user.pk, "jable", URL)
        try:
            assert image.read() == f"image-{index}".encode()
        finally:
            image.close()
    assert len(responses) == 2
    assert RecommendationCoverCacheService(sources[0]).get_cache_path(
        URL
    ) != RecommendationCoverCacheService(sources[1]).get_cache_path(URL)
    image = service.open(users[0].pk, "jable", URL)
    assert image.read() == b"image-0"
    image.close()
    assert len(responses) == 2
    for response, options in responses:
        assert options["proxy"] == "http://global-proxy.test:8080"
        assert options["allow_redirects"] is False
        assert not any(key.lower() == "cookie" for key in options["headers"])
        response.close.assert_called_once()


def test_revoke_after_open_blocks_stream_and_cached_hit(images):
    users, records, service, _, _ = images
    image = service.open(users[0].pk, "jable", URL)
    records.write(users[0].pk, "jable", {"expected_version": 1}, revoke=True)
    with pytest.raises(CredentialUnavailable):
        image.read(2)
    image.close()
    with pytest.raises(CredentialUnavailable):
        service.open(users[0].pk, "jable", URL)


def test_revoke_during_transfer_never_publishes(images, monkeypatch, tmp_path):
    users, records, service, _, _ = images
    response = Mock(status_code=200, headers={"Content-Type": "image/jpeg"})

    def chunks():
        yield b"first"
        records.write(users[0].pk, "jable", {"expected_version": 1}, revoke=True)
        yield b"late"

    response.iter_content.return_value = chunks()
    monkeypatch.setattr(
        "nassav.recommendation.cover_cache.requests.get", Mock(return_value=response)
    )
    with pytest.raises(CredentialUnavailable):
        service.open(users[0].pk, "jable", URL)
    assert not [path for path in tmp_path.rglob("*") if path.is_file()]
    response.close.assert_called_once()


def test_source_exit_failure_closes_open_handle(images, monkeypatch, tmp_path):
    users, _, service, _, _ = images
    opened = []

    def reader(path):
        handle = open_cache_image(tmp_path, path)
        opened.append(handle)
        return handle

    service.open_image = reader
    old = service.source_scope

    @contextmanager
    def failing_scope(*args):
        with old(*args) as source:
            yield source
            raise PermissionError("Account stopped")

    service.source_scope = failing_scope
    with pytest.raises((PermissionError, ReadLeaseNotFound)):
        service.open(users[0].pk, "jable", URL)
    assert opened and opened[0].closed


@pytest.mark.parametrize(
    "status,mime,chunks",
    [
        (302, "image/jpeg", [b"x"]),
        (200, "text/html", [b"x"]),
        (200, "image/jpeg", [b"x" * (5 * 1024 * 1024 + 1)]),
        (200, "image/jpeg", []),
    ],
)
def test_invalid_or_oversized_transfer_not_cached(
    images, monkeypatch, tmp_path, status, mime, chunks
):
    users, _, service, _, _ = images
    response = Mock(status_code=status, headers={"Content-Type": mime})
    response.iter_content.return_value = iter(chunks)
    monkeypatch.setattr(
        "nassav.recommendation.cover_cache.requests.get", Mock(return_value=response)
    )
    with pytest.raises(ReadLeaseNotFound):
        service.open(users[0].pk, "jable", URL)
    assert not [path for path in tmp_path.rglob("*") if path.is_file()]
    response.close.assert_called_once()


def test_symlink_cache_directory_cannot_be_read(tmp_path):
    root = tmp_path / "cache"
    root.mkdir()
    other = tmp_path / "other"
    other.mkdir()
    (other / "cover.jpg").write_bytes(b"private")
    (root / "scoped").symlink_to(other, target_is_directory=True)
    with pytest.raises(ReadLeaseNotFound):
        open_cache_image(root, root / "scoped/cover.jpg")


def owned_result(images, user=None):
    from nassav.models import RecommendationSnapshot, RecommendationItem
    from nassav.discovery_image_handles import recommendation_result

    users, records, _, _, _ = images
    user = user or users[0]
    source = Jable("http://global-proxy.test:8080")
    source.bind_credential_context(context(records, user.pk))
    proof = source_image_context(source)
    snapshot = RecommendationSnapshot.objects.create(
        owner=user,
        recommender_id="jable_page_lookup",
        strategy_id="local_preference",
        request_fingerprint="fixture",
        request_payload={"_image_contexts_v1": {"jable": proof}},
    )
    row = RecommendationItem.objects.create(
        snapshot=snapshot, rank=1, avid="IMAGE-001", source="Jable", cover_url=URL
    )
    payload = {
        "items": [
            {
                "snapshot_id": snapshot.pk,
                "avid": row.avid,
                "source": row.source,
                "cover_url": URL,
            }
        ]
    }
    result = recommendation_result(user.pk, payload)
    return row, result, proof


def test_http_scoped_stream_private_and_closes(images, monkeypatch):
    users, _, service, _, _ = images
    monkeypatch.setattr(
        "nassav.composition.build_recommendation_images", lambda user_id: service
    )
    client = APIClient()
    client.force_login(users[0])
    with override_settings(
        SOURCE_CREDENTIALS_ENABLED=True, NASSAV_OPERATOR_USERNAME=users[0].username
    ):
        rejected = client.get(
            "/nassav/api/recommendations/cover", {"url": URL, "source": "jable"}
        )
        assert rejected.status_code == 400
        _, result, _ = owned_result(images)
        response = client.get(
            "/nassav/api/recommendations/cover",
            {"handle": result["items"][0]["cover_handle"]},
        )
    assert response.status_code == 200
    assert response["Cache-Control"] == "private, no-cache"
    assert "Cookie" in response["Vary"]
    assert b"".join(response.streaming_content) == b"image-0"
    response.close()


def test_production_assembly_uses_global_proxy_and_account_epoch_fence(
    images, monkeypatch, settings
):
    from nassav import composition

    users, records, _, _, _ = images
    settings.PROXY_ENABLED = True
    settings.PROXY_URL = "http://global-proxy.test:8080"
    settings.SOURCE_CONFIG = {"jable": {"weight": 1}}

    def factories(proxy, browser, write_cookie, *, user_id):
        assert proxy == settings.PROXY_URL
        assert user_id == users[0].pk

        def source():
            result = Jable(proxy)
            result.bind_credential_context(context(records, user_id))
            return result

        return {"jable": source}

    factory = Mock(side_effect=factories)
    monkeypatch.setattr(composition, "source_factories", factory)
    service = composition.build_recommendation_images(users[0].pk)
    image = service.open(users[0].pk, "jable", URL)
    assert image.read(2) == b"im"
    users[0].is_active = False
    users[0].save(update_fields=["is_active"])
    with pytest.raises(PermissionError):
        image.read(2)
    image.close()
    with pytest.raises(PermissionError):
        service.open(users[1].pk, "jable", URL)
    assert factory.call_count == 1


def test_symlink_scope_cannot_redirect_publication(images, tmp_path):
    users, records, service, _, responses = images
    source = Jable()
    source.bind_credential_context(context(records, users[0].pk))
    path = RecommendationCoverCacheService(source).get_cache_path(URL)
    other = tmp_path / "outside"
    other.mkdir()
    path.parent.parent.mkdir()
    path.parent.symlink_to(other, target_is_directory=True)
    with pytest.raises(ReadLeaseNotFound):
        service.open(users[0].pk, "jable", URL)
    assert not responses and not list(other.iterdir())


def test_result_image_revalidation_rechecks_current_result(
    images, monkeypatch, settings
):
    settings.SOURCE_CREDENTIALS_ENABLED = True
    users, _, service, _, responses = images
    monkeypatch.setattr(
        "nassav.composition.build_recommendation_images", lambda user_id: service
    )
    client = APIClient()
    client.force_login(users[0])
    row, result, _ = owned_result(images)
    params = {"handle": result["items"][0]["cover_handle"]}
    with override_settings(
        SOURCE_CREDENTIALS_ENABLED=True, NASSAV_OPERATOR_USERNAME=users[0].username
    ):
        first = client.get("/nassav/api/recommendations/cover", params)
        etag = first["ETag"]
        assert b"".join(first.streaming_content) == b"image-0"
        first.close()
        second = client.get(
            "/nassav/api/recommendations/cover", params, HTTP_IF_NONE_MATCH=etag
        )
        assert second.status_code == 304
        assert second["Cache-Control"] == "private, no-cache"
        assert len(responses) == 1
        row.delete()
        rejected = client.get(
            "/nassav/api/recommendations/cover", params, HTTP_IF_NONE_MATCH=etag
        )
        assert rejected.status_code == 404
        assert len(responses) == 1
