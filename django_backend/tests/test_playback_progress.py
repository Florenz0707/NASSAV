from uuid import uuid4
from datetime import timedelta
import pytest
from django.utils import timezone
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from nassav.playback import records, progress
from nassav.playback.models import PlaybackProgress
from nassav.playback.policy import PlaybackGatewayError

pytestmark = pytest.mark.django_db


def ready(user, resource, login="one"):
    row = records.submit(user.pk, login, resource.avid, uuid4())
    row.state = "ready"
    row.save()
    return row


def payload(row, token, sequence=1, position=50):
    return {
        "session_generation": row.generation,
        "writer_generation": token["writer_generation"],
        "sequence": sequence,
        "expected_version": token["version"],
        "request_id": str(uuid4()),
        "position_seconds": position,
        "duration_seconds": 100,
        "completed": False,
    }


def claim(row, expected=0, command=None):
    return progress.claim(
        row.pk, row.user_id, "one", row.generation, command or uuid4(), expected
    )


def test_retries_backward_seek_takeover_and_clear(operator_user, resource_factory):
    row = ready(operator_user, resource_factory(source="Jable"))
    command = uuid4()
    token = claim(row, command=command)
    assert claim(row, command=command) == token
    body = payload(row, token)
    saved = progress.save(row.pk, row.user_id, "one", body)
    assert progress.save(row.pk, row.user_id, "one", body) == saved
    body2 = payload(row, saved, sequence=2, position=12)
    saved2 = progress.save(row.pk, row.user_id, "one", body2)
    assert saved2["position_seconds"] == 12
    with pytest.raises(PlaybackGatewayError):
        progress.save(row.pk, row.user_id, "one", body)
    other = ready(operator_user, row.resource)
    claim(other, expected=token["writer_generation"])
    with pytest.raises(PlaybackGatewayError):
        claim(row, command=command)
    with pytest.raises(PlaybackGatewayError):
        progress.save(row.pk, row.user_id, "one", payload(row, saved2, 3))
    progress.clear(row.user_id, row.resource.avid)
    assert progress.query(row)["position_seconds"] == 0
    with pytest.raises(PlaybackGatewayError):
        claim(other, expected=1)


def test_identity_user_isolation_deletion_and_completion(
    operator_user, resource_factory
):
    resource = resource_factory(source="Jable")
    row = ready(operator_user, resource)
    token = claim(row)
    body = payload(row, token, position=100)
    body["completed"] = True
    assert progress.save(row.pk, row.user_id, "one", body)["completed"]
    user2 = get_user_model().objects.create_user(username="second")
    other = ready(user2, resource)
    assert progress.query(other)["position_seconds"] == 0
    row.media_kind = "local"
    row.descriptor = {"marker": "one", "fingerprint": [1, 2, 3]}
    row.save()
    token = claim(row)
    progress.save(row.pk, row.user_id, "one", payload(row, token))
    row.descriptor = {"marker": "two", "fingerprint": [1, 2, 3]}
    row.save()
    assert progress.query(row)["position_seconds"] == 0
    resource.delete()
    assert PlaybackProgress.objects.count() == 2
    operator_user.delete()
    assert PlaybackProgress.objects.count() == 0


@pytest.mark.parametrize(
    "field,value",
    [
        ("position_seconds", float("nan")),
        ("duration_seconds", float("inf")),
        ("position_seconds", -1),
        ("position_seconds", 101),
        ("sequence", True),
        ("completed", "false"),
    ],
)
def test_invalid_values(operator_user, resource_factory, field, value):
    row = ready(operator_user, resource_factory())
    body = payload(row, claim(row))
    body[field] = value
    with pytest.raises(ValueError):
        progress.save(row.pk, row.user_id, "one", body)


def test_closed_expired_refreshed_and_wrong_login(operator_user, resource_factory):
    row = ready(operator_user, resource_factory())
    body = payload(row, claim(row))
    with pytest.raises(records.PlaybackSession.DoesNotExist):
        progress.save(row.pk, row.user_id, "other", body)
    row.generation += 1
    row.save()
    with pytest.raises(PlaybackGatewayError):
        progress.save(row.pk, row.user_id, "one", body)
    row.idle_expires_at = timezone.now() - timedelta(seconds=1)
    row.save()
    with pytest.raises(PlaybackGatewayError):
        progress.query(row)
    row.state = "closed"
    row.save()
    with pytest.raises(PlaybackGatewayError):
        claim(row)


def test_http_ownership_csrf_disabled_and_roundtrip(
    operator_user, resource_factory, settings
):
    settings.PLAYBACK_ENABLED = True
    client = APIClient()
    client.force_login(operator_user)
    row = ready(operator_user, resource_factory(), client.session.session_key)
    url = f"/nassav/api/playback-sessions/{row.pk}/progress"
    assert APIClient().get(url).status_code == 401
    assert client.get(url).data["data"]["restore_policy"] == "confirm"
    token = client.post(
        url + "/claim",
        {
            "session_generation": row.generation,
            "expected_writer_generation": 0,
            "request_id": str(uuid4()),
        },
        format="json",
    ).data["data"]
    body = payload(row, token)
    assert client.put(url, body, format="json").status_code == 200
    assert client.get(url).data["data"]["position_seconds"] == 50
    csrf = APIClient(enforce_csrf_checks=True)
    csrf.force_login(operator_user)
    assert csrf.put(url, body, format="json").status_code == 403
    assert csrf.get(url).status_code == 404
    assert (
        client.delete(
            f"/nassav/api/resources/{row.resource.avid}/playback-progress"
        ).status_code
        == 200
    )
    assert client.put(url, body, format="json").status_code == 409
    settings.PLAYBACK_ENABLED = False
    assert client.get(url).status_code == 404


@pytest.mark.django_db(transaction=True)
def test_concurrent_claims_have_one_owner(operator_user, resource_factory):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from django.db import close_old_connections

    one = ready(operator_user, resource_factory())
    two = ready(operator_user, one.resource)
    barrier = Barrier(2)

    def run(row):
        close_old_connections()
        try:
            barrier.wait(timeout=5)
            try:
                return claim(row)
            except PlaybackGatewayError as error:
                return error.code
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, [one, two]))
    assert sum(isinstance(value, dict) for value in results) == 1
    assert "progress_writer_conflict" in results
