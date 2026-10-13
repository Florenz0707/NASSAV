import pytest
from django.contrib.auth import get_user_model

from nassav.models import UserPreferences
from nassav.personal_state import update_state
from nassav.personal_preferences import update_preferences
from nassav.recommendation.seeds import LocalPreferenceSeedProvider

pytestmark = pytest.mark.django_db


def test_http_owner_filters_details_and_cache_validation(
    api_client, operator_user, resource_factory, actor_factory, genre_factory, settings
):
    first = resource_factory(avid="PRIVATE-001", watched=True, is_favorite=True)
    second = resource_factory(avid="PRIVATE-002")
    actor, genre = actor_factory(), genre_factory()
    first.actors.add(actor)
    first.genres.add(genre)
    other = get_user_model().objects.create_user(username="second")
    update_state(first, other.pk, {"notes": "另一个用户的秘密", "is_favorite": True})
    metadata_url = "/nassav/api/resource/metadata"
    before = api_client.get(metadata_url, {"avid": first.avid})
    assert not before.json()["data"]["is_favorite"]
    assert before.json()["data"]["notes"] == ""
    assert (
        api_client.get("/nassav/api/resources", {"is_favorite": "true"}).json()["data"]
        == []
    )
    patched = api_client.patch(
        f"/nassav/api/resource/{first.avid}/status",
        {
            "watched": True,
            "is_favorite": True,
            "notes": "私人备注",
            "expected_version": 0,
        },
        format="json",
    )
    assert patched.status_code == 200
    for params in [
        {"watched": "true"},
        {"is_favorite": "true"},
        {"actor": actor.pk, "is_favorite": "true"},
        {"genre": genre.pk, "watched": "true"},
    ]:
        listing = api_client.get("/nassav/api/resources", params).json()["data"]
        assert [r["avid"] for r in listing] == [first.avid]
        assert listing[0]["state_version"] == 1
        assert "notes" not in listing[0]
    unwatched = api_client.get("/nassav/api/resources", {"watched": "false"}).json()[
        "data"
    ]
    assert [r["avid"] for r in unwatched] == [second.avid]
    after = api_client.get(
        metadata_url, {"avid": first.avid}, HTTP_IF_NONE_MATCH=before["ETag"]
    )
    assert after.status_code == 200 and after["ETag"] != before["ETag"]
    assert after["Cache-Control"] == "private, no-cache"
    assert "Cookie" in after["Vary"]
    assert (
        api_client.get(
            metadata_url, {"avid": first.avid}, HTTP_IF_NONE_MATCH=after["ETag"]
        ).status_code
        == 304
    )
    assert (
        api_client.get(
            metadata_url,
            {"avid": first.avid},
            HTTP_IF_MODIFIED_SINCE=after["Last-Modified"],
        ).status_code
        == 200
    )
    conflict = api_client.patch(
        f"/nassav/api/resource/{first.avid}/status",
        {"notes": "迟到", "expected_version": 0},
        format="json",
    )
    assert (
        conflict.status_code == 409 and conflict.json()["data"]["notes"] == "私人备注"
    )
    settings.NASSAV_OPERATOR_USERNAME = other.username
    api_client.force_authenticate(user=other)
    own = api_client.get(
        metadata_url, {"avid": first.avid}, HTTP_IF_NONE_MATCH=after["ETag"]
    )
    assert own.status_code == 200
    assert own.json()["data"]["notes"] == "另一个用户的秘密"
    assert not own.json()["data"]["watched"]
    api_client.force_authenticate(user=None)
    assert api_client.get(metadata_url, {"avid": first.avid}).status_code == 401


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"watched": "true"},
        {"is_favorite": 1},
        {"notes": None},
        {"notes": 5},
        {"notes": "a" * 5001},
        {"notes": "text", "user_id": 2},
        {"rating": 3},
        {"watched": True, "expected_version": True},
    ],
)
def test_invalid_personal_updates_are_atomic(api_client, resource_factory, payload):
    resource = resource_factory()
    response = api_client.patch(
        f"/nassav/api/resource/{resource.avid}/status", payload, format="json"
    )
    assert response.status_code == 400
    assert not resource.user_states.exists()


def test_settings_never_touch_file_and_do_not_leak(
    api_client, operator_user, settings, tmp_path
):
    legacy = tmp_path / "user_settings.ini"
    legacy.write_text("[display]\ncolor_mode=light\n")
    legacy.chmod(0o400)
    settings.USER_SETTINGS_PATH = legacy
    assert api_client.get("/nassav/api/setting").json()["data"]["color_mode"] == "dark"
    assert not UserPreferences.objects.exists()
    assert (
        api_client.put(
            "/nassav/api/setting", {"color_mode": "light"}, format="json"
        ).status_code
        == 200
    )
    other = get_user_model().objects.create_user(username="second")
    settings.NASSAV_OPERATOR_USERNAME = other.username
    api_client.force_authenticate(user=other)
    assert api_client.get("/nassav/api/setting").json()["data"]["color_mode"] == "dark"
    assert (
        api_client.put(
            "/nassav/api/setting", {"font_family": "test"}, format="json"
        ).status_code
        == 200
    )
    assert (
        api_client.put(
            "/nassav/api/setting",
            {"color_mode": "light", "user_id": operator_user.pk},
            format="json",
        ).status_code
        == 400
    )
    assert legacy.read_text() == "[display]\ncolor_mode=light\n"
    legacy.unlink()
    assert api_client.get("/nassav/api/setting").json()["data"]["font_family"] == "test"
    assert not legacy.exists()


def test_default_search_source_and_recommendation_read_only_current_operator(
    operator_user, resource_factory, actor_factory
):
    from nassav.external_search import external_search_service

    other = get_user_model().objects.create_user(username="second")
    update_preferences(operator_user.pk, {"default_external_search_source": "missav"})
    assert (
        external_search_service.default_source("actor", user_id=operator_user.pk)
        == "missav"
    )
    assert external_search_service.default_source("actor", user_id=other.pk) == "jable"
    a, b = actor_factory(name="A"), actor_factory(name="B")
    r1, r2 = (
        resource_factory(avid="SEED-001"),
        resource_factory(avid="SEED-002", watched=True, is_favorite=True),
    )
    r1.actors.add(a)
    r2.actors.add(b)
    update_state(r1, operator_user.pk, {"watched": True, "is_favorite": True})
    update_state(r2, other.pk, {"watched": True, "is_favorite": True})
    seeds = LocalPreferenceSeedProvider().get_top_actor_seeds(10, only_interacted=True)
    assert [seed.value for seed in seeds] == [a.name]
