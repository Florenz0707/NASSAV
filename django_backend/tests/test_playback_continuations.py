from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4
import pytest
from django.utils import timezone
from rest_framework.test import APIClient
from nassav.playback import progress, records
from nassav.playback.continuations import list_continuations
from nassav.playback.models import PlaybackProgress
from nassav.playback.policy import PlaybackGatewayError
from nassav.playback.local_files import DjangoLocalVideoLocator


def ready(user, resource, login="one"):
    row = records.submit(user.pk, login, resource.avid, uuid4())
    row.state = "ready"
    row.save()
    return row


def claim(row):
    return progress.claim(row.pk, row.user_id, "one", row.generation, uuid4(), 0)


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


pytestmark = pytest.mark.django_db


def ledger(user, resource, **changes):
    defaults = {
        "media_key": "source-key",
        "media_kind": "source",
        "source": str(resource.source).lower(),
        "position_seconds": 30,
        "duration_seconds": 100,
    }
    return PlaybackProgress.objects.create(
        user=user, avid=resource.avid, **{**defaults, **changes}
    )


def empty_locator():
    return SimpleNamespace(identities=lambda avids: {})


def test_latest_ledger_filters_completion_deletion_and_other_users(
    operator_user, django_user_model, resource_factory
):
    user = operator_user
    other = django_user_model.objects.create_user(username="continue-other")
    first = resource_factory(avid="CONTINUE-1", source="Jable")
    second = resource_factory(avid="CONTINUE-2", source="Jable")
    ledger(user, first)
    ledger(other, second)
    assert [
        row["avid"]
        for row in list_continuations(user.pk, limit=6, locator=empty_locator())
    ] == [first.avid]
    # A completed newer ledger must not resurrect an unfinished older version.
    ledger(user, first, media_key="new-version", completed=True)
    assert list_continuations(user.pk, limit=6, locator=empty_locator()) == []
    personal = ledger(user, second)
    assert (
        list_continuations(user.pk, limit=6, locator=empty_locator())[0]["avid"]
        == second.avid
    )
    second.delete()
    assert PlaybackProgress.objects.filter(pk=personal.pk).exists()
    assert list_continuations(user.pk, limit=6, locator=empty_locator()) == []


def test_source_changes_tail_and_cleared_positions_are_excluded(
    operator_user, resource_factory
):
    for i, changes in enumerate(
        [{"source": "old-provider"}, {"position_seconds": 99}, {"position_seconds": 0}]
    ):
        resource = resource_factory(avid=f"EXCLUDE-{i}", source="Jable")
        ledger(operator_user, resource, **changes)
    assert list_continuations(operator_user.pk, limit=6, locator=empty_locator()) == []


def test_local_file_identity_is_rechecked_in_batched_projection(
    operator_user, resource_factory, tmp_path, django_assert_num_queries
):
    locator = DjangoLocalVideoLocator(tmp_path, tmp_path / "cover")
    resources = [
        resource_factory(avid=f"LOCAL-{i}", source="Jable", file_exists=True)
        for i in range(3)
    ]
    for resource in resources:
        (tmp_path / f"{resource.avid}.mp4").write_bytes(b"published")
        key = progress.media_key(
            SimpleNamespace(
                media_kind="local", descriptor=locator.identity(resource.avid)
            )
        )
        ledger(operator_user, resource, media_kind="local", media_key=key)
    with django_assert_num_queries(5):
        assert len(list_continuations(operator_user.pk, limit=6, locator=locator)) == 3
    (tmp_path / "LOCAL-1.mp4").write_bytes(b"new-publication")
    (tmp_path / "LOCAL-2.mp4").unlink()
    assert [
        row["avid"]
        for row in list_continuations(operator_user.pk, limit=6, locator=locator)
    ] == ["LOCAL-0"]


def test_writer_activity_cross_login_transfer_and_late_writer_rejection(
    operator_user, resource_factory
):
    resource = resource_factory(source="Jable")
    first = ready(operator_user, resource, login="one")
    first_token = claim(first)
    saved = progress.save(
        first.pk, operator_user.pk, "one", payload(first, first_token)
    )
    second = ready(operator_user, resource, login="two")
    seen = progress.query(second)
    assert seen["writer_active"] and not seen["is_writer"]
    # GET cannot claim or advance generations.
    assert progress.query(second)["writer_generation"] == saved["writer_generation"]
    transferred = progress.claim(
        second.pk,
        operator_user.pk,
        "two",
        second.generation,
        uuid4(),
        seen["writer_generation"],
    )
    assert transferred["writer_active"] and transferred["is_writer"]
    with pytest.raises(PlaybackGatewayError):
        progress.save(
            first.pk,
            operator_user.pk,
            "one",
            payload(first, saved, sequence=2, position=70),
        )
    records.PlaybackSession.objects.filter(pk=second.pk).update(
        idle_expires_at=timezone.now() - timedelta(seconds=1)
    )
    assert not progress.query(first)["writer_active"]


def test_http_list_privacy_disabled_and_strict_limits(
    api_client, operator_user, resource_factory, settings
):
    settings.PLAYBACK_ENABLED = True
    resource = resource_factory(avid="HTTP-CONTINUE", source="Jable")
    ledger(operator_user, resource)
    response = api_client.get("/nassav/api/playback-progress")
    assert response.status_code == 200 and response["Cache-Control"] == "no-store"
    item = response.json()["data"][0]
    assert item["avid"] == resource.avid
    assert not any(
        "url" in key or "writer" in key or "user" in key or "session" in key
        for key in item
    )
    for limit in ["0", "25", "bad", "1.5"]:
        assert (
            api_client.get(
                "/nassav/api/playback-progress", {"limit": limit}
            ).status_code
            == 400
        )
    anonymous = APIClient()
    assert anonymous.get("/nassav/api/playback-progress").status_code == 401
    settings.PLAYBACK_ENABLED = False
    assert api_client.get("/nassav/api/playback-progress").status_code == 404
