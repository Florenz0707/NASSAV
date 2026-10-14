from io import StringIO
from concurrent.futures import ThreadPoolExecutor

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import close_old_connections

from nassav.models import AVResource, UserPreferences, UserResourceState
from nassav.personal_preferences import read_preferences, update_preferences
from nassav.personal_state import (
    PersonalStateConflict,
    project_personal_state,
    state_snapshot,
    update_state,
)

pytestmark = pytest.mark.django_db


def test_defaults_isolation_patch_conflict_and_cascade(operator_user, resource_factory):
    resource = resource_factory(watched=True, is_favorite=True)
    other = get_user_model().objects.create_user(username="second")
    assert state_snapshot(resource, operator_user.pk)["watched"] is False
    first = update_state(
        resource, operator_user.pk, {"is_favorite": True}, expected_version=0
    )
    assert first["state_version"] == 1
    second = update_state(
        resource,
        operator_user.pk,
        {"notes": "私人备注\n<script>文本</script>"},
        expected_version=1,
    )
    assert second["is_favorite"] is True
    assert state_snapshot(resource, other.pk)["notes"] == ""
    with pytest.raises(PersonalStateConflict) as conflict:
        update_state(resource, operator_user.pk, {"notes": "迟到"}, expected_version=1)
    assert conflict.value.snapshot == second
    projected = project_personal_state(AVResource.objects.all(), other.pk).get(
        pk=resource.pk
    )
    assert projected.personal_watched is False
    assert projected.personal_is_favorite is False
    assert projected.personal_state_version == 0
    assert read_preferences(other.pk)["color_mode"] == "dark"
    update_preferences(operator_user.pk, {"color_mode": "light"})
    update_preferences(operator_user.pk, {"enable_avatar": "false"})
    assert read_preferences(operator_user.pk)["color_mode"] == "light"
    assert read_preferences(other.pk)["color_mode"] == "dark"
    resource.delete()
    assert not UserResourceState.objects.exists()
    operator_user.delete()
    assert not UserPreferences.objects.exists()


def test_import_explicit_owner_readonly_file_idempotent(
    operator_user, resource_factory, tmp_path
):
    resource = resource_factory(watched=True, is_favorite=True)
    other = get_user_model().objects.create_user(username="second")
    ini = tmp_path / "user_settings.ini"
    original = "[display]\ncolor_mode = light\nenable_avatar = false\n"
    ini.write_text(original)
    ini.chmod(0o400)
    opts = {
        "username": operator_user.username,
        "settings_file": ini,
        "stdout": StringIO(),
    }
    call_command("import_personal_data", **opts)
    assert not UserPreferences.objects.exists()
    with pytest.raises(CommandError):
        call_command("import_personal_data", username=other.username, apply=True)
    call_command("import_personal_data", apply=True, **opts)
    assert read_preferences(operator_user.pk)["color_mode"] == "light"
    assert state_snapshot(resource, operator_user.pk)["watched"]
    assert not UserPreferences.objects.filter(user=other).exists()
    update_state(resource, operator_user.pk, {"watched": False, "is_favorite": False})
    update_preferences(operator_user.pk, {"color_mode": "dark"})
    call_command("import_personal_data", apply=True, **opts)
    assert not state_snapshot(resource, operator_user.pk)["is_favorite"]
    assert read_preferences(operator_user.pk)["color_mode"] == "dark"
    assert ini.read_text() == original


def test_import_preserves_existing_state_and_settings_and_rejects_bad_file(
    operator_user, resource_factory, tmp_path
):
    resource = resource_factory(watched=True)
    update_state(resource, operator_user.pk, {"notes": "已编辑"})
    update_preferences(operator_user.pk, {"color_mode": "dark"})
    ini = tmp_path / "settings.ini"
    ini.write_text("[display]\ncolor_mode=invalid\n")
    with pytest.raises(CommandError):
        call_command(
            "import_personal_data",
            username=operator_user.username,
            settings_file=ini,
            apply=True,
        )
    assert UserPreferences.objects.get(user=operator_user).preferences == {
        "color_mode": "dark"
    }
    ini.write_text("[display]\ncolor_mode=light\n")
    call_command(
        "import_personal_data",
        username=operator_user.username,
        settings_file=ini,
        apply=True,
        stdout=StringIO(),
    )
    assert read_preferences(operator_user.pk)["color_mode"] == "dark"
    assert state_snapshot(resource, operator_user.pk)["notes"] == "已编辑"
    assert not state_snapshot(resource, operator_user.pk)["watched"]


@pytest.mark.django_db(transaction=True)
def test_concurrent_disjoint_patches_preserve_each_other(
    operator_user, resource_factory
):
    resource = resource_factory()

    def patch(changes):
        close_old_connections()
        try:
            return update_state(resource, operator_user.pk, changes)
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(patch, [{"watched": True}, {"notes": "并发备注"}]))
    assert sorted(row["state_version"] for row in results) == [1, 2]
    final = state_snapshot(resource, operator_user.pk)
    assert final["watched"] and final["notes"] == "并发备注"
