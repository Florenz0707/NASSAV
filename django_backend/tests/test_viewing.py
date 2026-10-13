from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import pytest
from django.db import close_old_connections
from nassav.personal_models import UserWatchHistory, UserResourceState
from nassav.personal_state import update_state, PersonalStateConflict
from nassav.playback import records
from nassav.playback.models import PlaybackProgress
from nassav.playback.policy import PlaybackGatewayError
from nassav.viewing import record_view, list_viewing

pytestmark = pytest.mark.django_db


def ready(user, resource, key="view"):
    row = records.submit(user.pk, key, resource.avid, uuid4())
    row.state = "ready"
    row.save()
    return row


def test_real_view_deduplicates_and_moves_to_front_without_progress_claim(
    operator_user, resource_factory
):
    a, b = resource_factory(avid="VIEW-1"), resource_factory(avid="VIEW-2")
    first = ready(operator_user, a)
    second = ready(operator_user, b)
    assert list_viewing(operator_user.pk, "history", 1, 15)[0] == []
    record_view(first.pk, operator_user.pk, "view", 1, 1)
    record_view(second.pk, operator_user.pk, "view", 1, 1)
    assert [x["avid"] for x in list_viewing(operator_user.pk, "history", 1, 15)[0]] == [
        b.avid,
        a.avid,
    ]
    records.close(first.pk, operator_user.pk, "view", first.version, uuid4())
    third = ready(operator_user, a)
    record_view(third.pk, operator_user.pk, "view", 1, 1)
    stamp = UserWatchHistory.objects.get(resource=a).last_watched_at
    # Previous session retry must never reorder history; refresh in same session also dedupes.
    record_view(second.pk, operator_user.pk, "view", 1, 1)
    third.generation = 2
    third.save(update_fields=["generation"])
    record_view(third.pk, operator_user.pk, "view", 2, 1)
    assert UserWatchHistory.objects.count() == 2
    assert UserWatchHistory.objects.get(resource=a).last_watched_at == stamp
    assert [x["avid"] for x in list_viewing(operator_user.pk, "history", 1, 1)[0]] == [
        a.avid
    ]
    assert not PlaybackProgress.objects.exists()
    record_view(second.pk, operator_user.pk, "view", 1, 2)
    assert list_viewing(operator_user.pk, "history", 1, 15)[0][0]["avid"] == b.avid
    record_view(third.pk, operator_user.pk, "view", 2, 1)
    assert list_viewing(operator_user.pk, "history", 1, 15)[0][0]["avid"] == b.avid
    assert (
        not UserResourceState.objects.exists()
    )  # Does not mark watched or remove later.


def test_ownership_generation_terminal_expiry_and_cascade(
    operator_user, django_user_model, resource_factory
):
    resource = resource_factory()
    row = ready(operator_user, resource)
    other = django_user_model.objects.create_user(username="view-other")
    for user_id, key in [(other.pk, "view"), (operator_user.pk, "other-login")]:
        with pytest.raises(records.PlaybackSession.DoesNotExist):
            record_view(row.pk, user_id, key, 1, 1)
    with pytest.raises(PlaybackGatewayError):
        record_view(row.pk, operator_user.pk, "view", 2, 1)
    for value in [True, "1", 0, None]:
        with pytest.raises(ValueError):
            record_view(row.pk, operator_user.pk, "view", value, 1)
    record_view(row.pk, operator_user.pk, "view", 1, 1)
    assert list_viewing(other.pk, "history", 1, 15)[0] == []
    records.close(row.pk, operator_user.pk, "view", row.version, uuid4())
    with pytest.raises(PlaybackGatewayError):
        record_view(row.pk, operator_user.pk, "view", 1, 1)
    resource.delete()
    assert not UserWatchHistory.objects.exists()


def test_watch_later_partial_conflict_dedup_order_and_removal(
    operator_user, django_user_model, resource_factory
):
    a, b = resource_factory(avid="LATER-1"), resource_factory(avid="LATER-2")
    other = django_user_model.objects.create_user(username="later-other")
    update_state(a, operator_user.pk, {"watch_later": True})
    stamp = UserResourceState.objects.get(resource=a).watch_later_added_at
    update_state(b, operator_user.pk, {"watch_later": True})
    update_state(a, operator_user.pk, {"watch_later": True, "notes": "保留"})
    assert UserResourceState.objects.get(resource=a).watch_later_added_at == stamp
    data, pagination = list_viewing(operator_user.pk, "watch-later", 1, 1)
    assert data[0]["avid"] == b.avid and data[0]["watch_later"] is True
    assert pagination == {"page": 1, "pages": 2, "page_size": 1, "total": 2}
    assert list_viewing(other.pk, "watch-later", 1, 15)[0] == []
    with pytest.raises(PersonalStateConflict):
        update_state(a, operator_user.pk, {"watch_later": False}, expected_version=1)
    update_state(a, operator_user.pk, {"watch_later": False}, expected_version=2)
    assert UserResourceState.objects.get(resource=a).notes == "保留"
    update_state(a, operator_user.pk, {"watch_later": True})
    assert list_viewing(operator_user.pk, "watch-later", 1, 15)[0][0]["avid"] == a.avid
    a.delete()
    assert list_viewing(operator_user.pk, "watch-later", 99, 15)[1]["total"] == 1


def test_http_no_store_validation_and_owned_playing(
    api_client, operator_user, resource_factory, settings
):
    resource = resource_factory()
    assert api_client.get("/nassav/api/personal/history").json()["data"] == []
    response = api_client.patch(
        f"/nassav/api/resource/{resource.avid}/status",
        {"watch_later": True, "expected_version": 0},
        format="json",
    )
    assert (
        response.status_code == 200 and response.json()["data"]["watch_later"] is True
    )
    response = api_client.get("/nassav/api/personal/watch-later")
    assert (
        response.status_code == 200 and response["Cache-Control"] == "private, no-store"
    )
    assert response.json()["data"][0]["avid"] == resource.avid
    for params in [{"page": 0}, {"page_size": 201}, {"page": "bad"}]:
        assert api_client.get("/nassav/api/personal/history", params).status_code == 400
    settings.PLAYBACK_ENABLED = True
    row = ready(operator_user, resource, api_client.session.session_key)
    response = api_client.post(
        f"/nassav/api/playback-sessions/{row.pk}/viewed",
        {"session_generation": 1, "sequence": 1},
        format="json",
    )
    assert response.status_code == 200
    assert (
        api_client.get("/nassav/api/personal/history").json()["data"][0]["avid"]
        == resource.avid
    )


@pytest.mark.django_db(transaction=True)
def test_concurrent_history_is_unique_and_old_session_retry_is_idempotent(
    operator_user, resource_factory
):
    row = ready(operator_user, resource_factory())

    def run(_):
        close_old_connections()
        try:
            return record_view(row.pk, operator_user.pk, "view", 1, 1)
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, range(2)))
    assert results[0] == results[1]
    assert UserWatchHistory.objects.count() == 1
