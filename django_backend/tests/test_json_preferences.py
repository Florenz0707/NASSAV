from concurrent.futures import ThreadPoolExecutor
from io import StringIO

import pytest
from django.core.management import call_command
from django.db import close_old_connections

from nassav.models import UserPreferences
from nassav.personal_preferences import read_preferences, update_preferences
from nassav.preference_definitions import PREFERENCE_DEFINITIONS, PreferenceDefinition

pytestmark = pytest.mark.django_db


def test_defaults_sparse_updates_and_noop_timestamps(api_client, operator_user):
    def get():
        return api_client.get("/nassav/api/setting").json()["data"]

    assert get()["color_mode"] == "dark"
    assert not UserPreferences.objects.exists()
    assert api_client.put("/nassav/api/setting", {}, format="json").status_code == 200
    assert not UserPreferences.objects.exists()
    response = api_client.put(
        "/nassav/api/setting", {"color_mode": "light"}, format="json"
    )
    assert response.status_code == 200
    row = UserPreferences.objects.get(user=operator_user)
    assert row.preferences == {"color_mode": "light"}
    created, updated = row.created_at, row.updated_at
    assert response.json()["data"]["enable_avatar"] == "true"
    assert get()["font_family"] == "Mplus2"
    for body in [{}, {"color_mode": "light"}]:
        assert (
            api_client.put("/nassav/api/setting", body, format="json").status_code
            == 200
        )
        row.refresh_from_db()
        assert row.updated_at == updated
        assert row.created_at == created
    update_preferences(operator_user.pk, {"enable_avatar": "false"})
    row.refresh_from_db()
    assert row.preferences == {"color_mode": "light", "enable_avatar": "false"}
    assert row.created_at == created and row.updated_at > updated


def test_new_keys_default_without_backfill_and_typed_validation(
    api_client, operator_user, monkeypatch
):
    row = UserPreferences.objects.create(
        user=operator_user, preferences={"color_mode": "light"}
    )
    stamp = row.updated_at
    monkeypatch.setitem(
        PREFERENCE_DEFINITIONS, "show_badges", PreferenceDefinition(True)
    )
    assert api_client.get("/nassav/api/setting").json()["data"]["show_badges"] is True
    row.refresh_from_db()
    assert row.preferences == {"color_mode": "light"} and row.updated_at == stamp
    assert (
        api_client.put(
            "/nassav/api/setting", {"show_badges": "false"}, format="json"
        ).status_code
        == 400
    )
    monkeypatch.setitem(
        PREFERENCE_DEFINITIONS, "show_badges", PreferenceDefinition(False)
    )
    assert api_client.get("/nassav/api/setting").json()["data"]["show_badges"] is False
    assert (
        api_client.put(
            "/nassav/api/setting", {"show_badges": False}, format="json"
        ).status_code
        == 200
    )
    assert read_preferences(operator_user.pk)["show_badges"] is False
    monkeypatch.setitem(
        PREFERENCE_DEFINITIONS, "show_badges", PreferenceDefinition(True)
    )
    assert read_preferences(operator_user.pk)["show_badges"] is False


def test_removed_or_renamed_keys_inactive_without_destructive_put(
    api_client, operator_user, monkeypatch
):
    row = UserPreferences.objects.create(
        user=operator_user,
        preferences={"color_mode": "light", "future_key": {"data": 1}},
    )
    monkeypatch.delitem(PREFERENCE_DEFINITIONS, "color_mode")
    monkeypatch.setitem(
        PREFERENCE_DEFINITIONS, "theme", PreferenceDefinition("dark", ("light", "dark"))
    )
    result = api_client.get("/nassav/api/setting").json()["data"]
    assert "color_mode" not in result and "future_key" not in result
    assert result["theme"] == "dark"  # A rename requires an explicit data migration.
    assert (
        api_client.put(
            "/nassav/api/setting",
            {"color_mode": "light", "font_family": "Valid"},
            format="json",
        ).status_code
        == 400
    )
    row.refresh_from_db()
    assert "font_family" not in row.preferences
    assert (
        api_client.put(
            "/nassav/api/setting", {"theme": "light"}, format="json"
        ).status_code
        == 200
    )
    row.refresh_from_db()
    assert row.preferences["color_mode"] == "light"
    assert row.preferences["future_key"] == {"data": 1}
    assert read_preferences(operator_user.pk)["theme"] == "light"


@pytest.mark.parametrize(
    "stored",
    [
        {"color_mode": 1, "font_family": [], "enable_avatar": False},
        ["bad root"],
        "bad root",
    ],
)
def test_invalid_stored_values_return_defaults_without_writes(
    api_client, operator_user, stored
):
    row = UserPreferences.objects.create(user=operator_user, preferences=stored)
    stamp = row.updated_at
    result = api_client.get("/nassav/api/setting")
    assert result.status_code == 200
    assert result.json()["data"]["color_mode"] == "dark"
    assert result.json()["data"]["font_family"] == "Mplus2"
    assert result.json()["data"]["enable_avatar"] == "true"
    row.refresh_from_db()
    assert row.updated_at == stamp


@pytest.mark.parametrize(
    "body",
    [
        {"color_mode": True},
        {"font_family": 1},
        {"enable_avatar": False},
        {"font_family": "x" * 101},
        {"unknown": 1},
        {"user_id": 2},
        {"color_mode": None},
        ["bad root"],
    ],
)
def test_bad_updates_are_atomic_and_never_create_settings(api_client, body):
    assert api_client.put("/nassav/api/setting", body, format="json").status_code == 400
    assert not UserPreferences.objects.exists()


def test_import_without_ini_does_not_create_preferences(
    operator_user, resource_factory
):
    resource_factory(watched=True)
    call_command(
        "import_personal_data",
        username=operator_user.username,
        apply=True,
        stdout=StringIO(),
    )
    assert not UserPreferences.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_concurrent_json_partial_updates_preserve_values(operator_user):
    def patch(body):
        close_old_connections()
        try:
            update_preferences(operator_user.pk, body)
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(patch, [{"color_mode": "light"}, {"enable_avatar": "false"}]))
    assert UserPreferences.objects.get(user=operator_user).preferences == {
        "color_mode": "light",
        "enable_avatar": "false",
    }


def test_json_null_root_does_not_escape_default_projection(api_client, operator_user):
    from django.db.models import Value, JSONField

    row = UserPreferences.objects.create(user=operator_user)
    UserPreferences.objects.filter(pk=row.pk).update(
        preferences=Value(None, output_field=JSONField())
    )
    row.refresh_from_db()
    assert row.preferences is None
    assert api_client.get("/nassav/api/setting").json()["data"]["color_mode"] == "dark"
    row.refresh_from_db()
    assert row.preferences is None


@pytest.mark.parametrize(
    "default, stored_value, submitted", [(True, 0, False), (1.0, 0, 0.0)]
)
def test_put_repairs_equal_but_wrong_json_type(
    api_client, operator_user, monkeypatch, default, stored_value, submitted
):
    monkeypatch.setitem(
        PREFERENCE_DEFINITIONS, "typed_setting", PreferenceDefinition(default)
    )
    row = UserPreferences.objects.create(
        user=operator_user, preferences={"typed_setting": stored_value}
    )
    response = api_client.put(
        "/nassav/api/setting", {"typed_setting": submitted}, format="json"
    )
    assert response.status_code == 200
    assert response.json()["data"]["typed_setting"] == submitted
    row.refresh_from_db()
    assert type(row.preferences["typed_setting"]) is type(submitted)
