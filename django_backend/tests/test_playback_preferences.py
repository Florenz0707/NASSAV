import pytest
from nassav.personal_preferences import read_preferences, update_preferences
from nassav.preference_definitions import InvalidPreference

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    "key,value",
    [
        ("playback_volume", -0.1),
        ("playback_volume", 1.1),
        ("playback_volume", True),
        ("playback_volume", "0.5"),
        ("playback_rate", 3),
        ("playback_rate", "1.5"),
        ("playback_rate", False),
        ("playback_muted", "false"),
        ("playback_default_mode", "unknown"),
    ],
)
def test_invalid_playback_preferences_reject_whole_patch(operator_user, key, value):
    with pytest.raises(InvalidPreference):
        update_preferences(operator_user.pk, {"color_mode": "light", key: value})
    assert read_preferences(operator_user.pk)["color_mode"] == "dark"


def test_playback_preferences_are_personal_and_defaults_do_not_write(
    api_client, operator_user, django_user_model
):
    from nassav.models import UserPreferences

    other = django_user_model.objects.create_user(username="other-playback")
    defaults = read_preferences(other.pk)
    assert defaults["playback_volume"] == 0.8 and defaults["playback_rate"] == 1
    assert not UserPreferences.objects.exists()
    body = {
        "playback_volume": 0,
        "playback_muted": True,
        "playback_rate": 1.5,
        "playback_subtitles_enabled": False,
        "playback_default_mode": "local",
    }
    response = api_client.put("/nassav/api/setting", body, format="json")
    assert response.status_code == 200
    assert all(response.json()["data"][key] == value for key, value in body.items())
    assert read_preferences(other.pk) == defaults
    assert (
        api_client.put(
            "/nassav/api/setting",
            {"playback_volume": 1, "playback_rate": 1},
            format="json",
        ).status_code
        == 200
    )
