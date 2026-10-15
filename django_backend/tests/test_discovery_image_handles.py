"""Owned recommendation/Redis-result references with real credentials and files."""

from copy import deepcopy
from types import SimpleNamespace

import pytest
from nassav.discovery_image_handles import (
    recommendation_result,
    search_snapshot,
    resolve,
)
from nassav.resource_reads import ReadLeaseNotFound
from nassav.account_models import UserAccount
from nassav.models import RecommendationItem
from test_scoped_recommendation_images import images as images, owned_result, URL
from test_scoped_source_runtime import runtime as runtime

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def scoped(settings):
    settings.SOURCE_CREDENTIALS_ENABLED = True


def test_recommendation_projection_is_batched_and_strips_unowned_or_forged_handles(
    images, django_assert_num_queries
):
    users, _, _, _, _ = images
    row, result, _ = owned_result(images)
    other, _, _ = owned_result(images, users[1])
    original = deepcopy(result)
    result["items"].append(
        {
            "snapshot_id": other.snapshot_id,
            "avid": other.avid,
            "source": other.source,
            "cover_url": URL,
            "cover_handle": "forged",
        }
    )
    with django_assert_num_queries(2):
        projected = recommendation_result(users[0].pk, result)
    assert projected["items"][0]["cover_handle"]
    assert "cover_handle" not in projected["items"][1]
    assert original["items"][0]["cover_handle"] == result["items"][0]["cover_handle"]
    ref = resolve(users[0].pk, projected["items"][0]["cover_handle"])
    assert ref.source == "jable" and ref.url == URL
    assert row.pk


def test_other_owner_tampered_token_and_changed_item_never_fetch(images):
    users, _, _, _, responses = images
    row, result, _ = owned_result(images)
    handle = result["items"][0]["cover_handle"]
    for actor, token in [(users[1], handle), (users[0], handle + "tamper")]:
        with pytest.raises(ReadLeaseNotFound):
            resolve(actor.pk, token)
    RecommendationItem.objects.filter(pk=row.pk).update(cover_url=URL + "?changed")
    with pytest.raises(ReadLeaseNotFound):
        resolve(users[0].pk, handle)
    assert not responses


def test_missing_historical_proof_stays_placeholder_without_guessing_scope(images):
    users, _, _, _, responses = images
    row, result, _ = owned_result(images)
    row.snapshot.request_payload = {}
    row.snapshot.save()
    projected = recommendation_result(users[0].pk, result)
    assert "cover_handle" not in projected["items"][0]
    assert not responses


def test_scope_change_rejects_old_image_even_before_cache_transport(images):
    users, records, service, _, responses = images
    _, result, _ = owned_result(images)
    ref = resolve(users[0].pk, result["items"][0]["cover_handle"])
    records.write(
        users[0].pk,
        "jable",
        {
            "expected_version": 1,
            "cookie": "account_session=new-account",
            "user_agent": "new-agent",
        },
    )
    with pytest.raises(ReadLeaseNotFound, match="context changed"):
        service.open(
            users[0].pk,
            ref.source,
            ref.url,
            expected_context=ref.context,
            check_result=ref.check,
        )
    assert not responses


def test_history_reset_and_account_epoch_change_block_open_stream(images):
    users, _, service, _, _ = images
    row, result, _ = owned_result(images)
    ref = resolve(users[0].pk, result["items"][0]["cover_handle"])
    image = service.open(
        users[0].pk,
        ref.source,
        ref.url,
        expected_context=ref.context,
        check_result=ref.check,
    )
    assert image.read(2) == b"im"
    row.snapshot.delete()
    try:
        with pytest.raises(ReadLeaseNotFound):
            image.read(2)
    finally:
        image.close()
    _, result, _ = owned_result(images)
    UserAccount.objects.create(user=users[0], role="user", version=2)
    with pytest.raises(ReadLeaseNotFound, match="account changed"):
        resolve(users[0].pk, result["items"][0]["cover_handle"])


def search_result(images):
    users, _, _, _, _ = images
    _, _, proof = owned_result(images)
    row = {"avid": "IMAGE-001", "source": "Jable", "thumbnail_url": URL}
    snapshot = {
        "task_id": "search-a",
        "owner_id": users[0].pk,
        "owner_epoch": 0,
        "state": "running",
        "query": {"source": "jable", "source_context": proof},
        "collected_results": [row],
        "result": {"data": {"external_results": [row]}, "pagination": {"page": 1}},
    }
    values = {"search-a": snapshot}
    store = SimpleNamespace(get=lambda identity: deepcopy(values.get(identity)))
    projected = search_snapshot(users[0].pk, snapshot)
    return (
        users,
        snapshot,
        values,
        store,
        projected["result"]["data"]["external_results"][0]["cover_handle"],
    )


def test_partial_search_handle_owns_exact_result_and_expires_with_snapshot(images):
    users, snapshot, values, store, handle = search_result(images)
    ref = resolve(users[0].pk, handle, search_store=store)
    assert ref.url == URL
    assert "cover_handle" not in snapshot["result"]["data"]["external_results"][0]
    with pytest.raises(ReadLeaseNotFound):
        resolve(users[1].pk, handle, search_store=store)
    values.clear()
    with pytest.raises(ReadLeaseNotFound):
        ref.check()
    with pytest.raises(ReadLeaseNotFound):
        resolve(users[0].pk, handle, search_store=store)


def test_search_source_change_or_result_replacement_does_not_reauthorize_cached_image(
    images,
):
    users, _, values, store, handle = search_result(images)
    values["search-a"]["query"]["source_context"][1] = "new-context"
    with pytest.raises(ReadLeaseNotFound):
        resolve(users[0].pk, handle, search_store=store)
    projected = search_snapshot(users[0].pk, values["search-a"])
    handle = projected["result"]["data"]["external_results"][0]["cover_handle"]
    values["search-a"]["collected_results"][0]["thumbnail_url"] = (
        "https://assets-cdn.jable.tv/other.jpg"
    )
    with pytest.raises(ReadLeaseNotFound):
        resolve(users[0].pk, handle, search_store=store)


def test_workflow_persists_private_image_proof_and_does_not_put_it_in_public_effective_request(
    images,
):
    from nassav.recommendation.workflow import RecommenderManager
    from nassav.recommendation.entities import (
        RecommendationCandidate,
        RecommendationRun,
    )
    from nassav.recommendation.repository import RecommendationSnapshotRepository

    users, _, _, _, _ = images
    _, _, proof = owned_result(images)
    repository = RecommendationSnapshotRepository(users[0].pk)
    context = SimpleNamespace(
        next_random_seed=lambda: 1,
        prepare=lambda *args: "proof-test",
        persist=lambda execution: repository.save_execution(execution).pk,
    )
    runner = SimpleNamespace(
        recommend=lambda request: RecommendationRun(
            [],
            [
                RecommendationCandidate(
                    "IMAGE-002", "title", "https://jable.tv/test", URL
                )
            ],
        )
    )
    manager = RecommenderManager(
        context,
        {"jable_page_lookup": lambda strategy: runner},
        image_contexts=lambda: {"jable": proof},
    )
    execution = manager.recommend()
    row = RecommendationItem.objects.get(snapshot_id=execution.snapshot_id)
    assert row.snapshot.request_payload["_image_contexts_v1"] == {"jable": proof}
    assert "_image_contexts_v1" not in str(execution.to_dict())
    assert recommendation_result(users[0].pk, execution.to_dict())["items"][0][
        "cover_handle"
    ]


def test_search_image_filled_from_scoped_details_resolves_same_read_only_projection(
    images,
):
    users, snapshot, values, store, _ = search_result(images)
    values["search-a"]["collected_results"][0]["thumbnail_url"] = ""
    values["search-a"]["result"]["data"]["external_results"][0]["thumbnail_url"] = ""
    polled = deepcopy(values["search-a"])
    polled["result"]["data"]["external_results"][0]["thumbnail_url"] = URL
    projected = search_snapshot(users[0].pk, polled)
    handle = projected["result"]["data"]["external_results"][0]["cover_handle"]
    calls = []

    def cached(source, rows, *, force):
        calls.append((source, force, rows[0]["avid"]))
        return [{**rows[0], "thumbnail_url": URL}], 1

    reference = resolve(
        users[0].pk, handle, search_store=store, detail_projection=cached
    )
    assert reference.url == URL and calls == [("jable", False, "IMAGE-001")]
    with pytest.raises(ReadLeaseNotFound):
        resolve(
            users[0].pk,
            handle,
            search_store=store,
            detail_projection=lambda *args, **kwargs: ([], 0),
        )


def test_reset_during_image_transfer_stops_and_does_not_publish_cache(
    images, monkeypatch, tmp_path
):
    from unittest.mock import Mock

    users, _, service, _, _ = images
    row, result, _ = owned_result(images)
    reference = resolve(users[0].pk, result["items"][0]["cover_handle"])
    response = Mock(status_code=200, headers={"Content-Type": "image/png"})

    def chunks():
        yield b"first"
        row.snapshot.delete()
        yield b"late"

    response.iter_content.return_value = chunks()
    monkeypatch.setattr(
        "nassav.recommendation.cover_cache.requests.get", Mock(return_value=response)
    )
    with pytest.raises(ReadLeaseNotFound):
        service.open(
            users[0].pk,
            reference.source,
            reference.url,
            expected_context=reference.context,
            check_result=reference.check,
        )
    assert not [path for path in tmp_path.rglob("*") if path.is_file()]
    response.close.assert_called_once()


def test_unchanged_results_keep_stable_image_urls_across_poll_times(
    images, monkeypatch
):
    from django.core import signing

    users, _, _, _, _ = images
    _, payload, _ = owned_result(images)
    first = recommendation_result(users[0].pk, payload)["items"][0]["cover_handle"]
    monkeypatch.setattr(signing.time, "time", lambda: 123456789)
    second = recommendation_result(users[0].pk, payload)["items"][0]["cover_handle"]
    assert first == second
    assert resolve(users[0].pk, second).url == URL
