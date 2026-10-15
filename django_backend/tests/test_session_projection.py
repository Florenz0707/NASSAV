"""Real login sessions expose only own cache identity and explicit capabilities."""

import pytest
from django.test import Client
from django.contrib.auth import get_user_model
from nassav.account_models import UserAccount

pytestmark = pytest.mark.django_db


def test_anonymous_and_non_operator_sessions_disclose_no_account_metadata(
    operator_user,
):
    client = Client()
    data = client.get("/nassav/api/auth/session").json()["data"]
    assert data["authenticated"] is False and data["cache_identity"] is None
    assert data["capabilities"] == {} and data["user_id"] is None
    other = get_user_model().objects.create_user(
        "other-projection", password="test-password", is_superuser=True
    )
    UserAccount.objects.create(user=other, role="admin")
    client.force_login(other)
    assert client.get("/nassav/api/auth/session").json()["data"] == data


def test_identity_is_stable_read_only_and_changes_for_login_role_and_features(
    operator_user, settings
):
    client = Client()
    client.force_login(operator_user)
    first = client.get("/nassav/api/auth/session").json()["data"]
    assert first["capabilities"]["ordinary_login"] is False
    assert first["capabilities"]["app_admin"] is False
    assert first["user_id"] == operator_user.pk and first["account_epoch"] == 0
    assert first["cache_identity"] != client.session.session_key
    assert client.get("/nassav/api/auth/session").json()["data"] == first
    assert not UserAccount.objects.filter(user=operator_user).exists()
    role = UserAccount.objects.create(user=operator_user, role="admin")
    second = client.get("/nassav/api/auth/session").json()["data"]
    assert second["capabilities"]["app_admin"] is True
    assert second["cache_identity"] != first["cache_identity"]
    role.role, role.version = "user", role.version + 1
    role.save()
    third = client.get("/nassav/api/auth/session").json()["data"]
    assert third["cache_identity"] != second["cache_identity"]
    settings.SHARED_LIBRARY_ENABLED = True
    fourth = client.get("/nassav/api/auth/session").json()["data"]
    assert fourth["capabilities"]["shared_library"] is True
    assert fourth["capabilities"]["legacy_asset_controls"] is False
    assert fourth["cache_identity"] != third["cache_identity"]
    client.logout()
    client.force_login(operator_user)
    assert (
        client.get("/nassav/api/auth/session").json()["data"]["cache_identity"]
        != fourth["cache_identity"]
    )


def test_login_and_session_share_the_same_non_secret_identity(operator_user):
    client = Client()
    logged = client.post(
        "/nassav/api/auth/login",
        {"username": operator_user.username, "password": "p0-p1-test-only-password"},
        content_type="application/json",
    )
    assert logged.status_code == 200
    response = client.get("/nassav/api/auth/session")
    assert response.json()["data"] == logged.json()["data"]
    assert response["Cache-Control"] == "no-store"
    assert (
        "password" not in str(response.json())
        and "cookie" not in str(response.json()).lower()
    )
