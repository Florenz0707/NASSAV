"""Managed login + browser preconditions, alongside existing object authorization."""

from uuid import uuid4

import pytest
from rest_framework.test import APIClient
from nassav.account_models import UserAccount
from nassav.personal_models import UserPreferences
from nassav.personal_preferences import read_preferences
from nassav.models import AVResource
from nassav.library_models import ResourcePoolEntry, UserLibraryEntry
from nassav.access import is_admitted, is_operator

pytestmark = pytest.mark.django_db


@pytest.fixture
def managed(settings, django_user_model):
    settings.MULTI_USER_ENABLED = True
    settings.SHARED_LIBRARY_ENABLED = True
    settings.SOURCE_CREDENTIALS_ENABLED = True
    admin = django_user_model.objects.create_user(
        username="managed-admin", password="Temporary-Managed-Admin-12!"
    )
    member = django_user_model.objects.create_user(
        username="managed-member",
        password="Temporary-Managed-Member-12!",
        is_staff=True,
        is_superuser=True,
    )
    UserAccount.objects.create(user=admin, role="admin")
    UserAccount.objects.create(user=member, role="user")
    return admin, member


def browser(user):
    client = APIClient(enforce_csrf_checks=True)
    client.force_login(user)
    snapshot = client.get("/nassav/api/auth/session").json()["data"]
    assert snapshot["authenticated"]
    client.credentials(
        HTTP_X_NASSAV_CONTEXT=snapshot["cache_identity"],
        HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value,
    )
    return client, snapshot


def test_ordinary_login_is_explicit_managed_admission_not_django_flags(
    managed, django_user_model, settings
):
    _, member = managed
    assert not is_operator(member) and is_admitted(member)
    client = APIClient(enforce_csrf_checks=True)
    client.get("/nassav/api/auth/session")
    response = client.post(
        "/nassav/api/auth/login",
        {"username": member.username, "password": "Temporary-Managed-Member-12!"},
        format="json",
        HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value,
    )
    assert response.status_code == 200
    assert response.json()["data"]["capabilities"]["ordinary_login"] is True
    assert response.json()["data"]["capabilities"]["app_admin"] is False
    unknown = django_user_model.objects.create_user(
        username="unmanaged-staff", is_superuser=True, is_staff=True
    )
    assert not is_admitted(unknown)
    settings.MULTI_USER_ENABLED = False
    assert not is_admitted(member)
    settings.MULTI_USER_ENABLED = True
    settings.SHARED_LIBRARY_ENABLED = False
    assert not is_admitted(member)


def test_missing_stale_and_other_login_context_cannot_read_or_write_new_cookie_user(
    managed,
):
    admin, member = managed
    first, first_session = browser(admin)
    second, second_session = browser(member)
    for identity in ["", first_session["cache_identity"]]:
        second.credentials(
            HTTP_X_NASSAV_CONTEXT=identity,
            HTTP_X_CSRFTOKEN=second.cookies["csrftoken"].value,
        )
        response = second.put(
            "/nassav/api/setting", {"enable_avatar": "false"}, format="json"
        )
        assert response.status_code == 409
        assert response.json()["data"]["error_code"] == "browser_context_changed"
        assert second.get("/nassav/api/setting").status_code == 409
    assert not UserPreferences.objects.filter(user=member).exists()
    second.credentials(
        HTTP_X_NASSAV_CONTEXT=second_session["cache_identity"],
        HTTP_X_CSRFTOKEN=second.cookies["csrftoken"].value,
    )
    assert (
        second.put(
            "/nassav/api/setting", {"enable_avatar": "false"}, format="json"
        ).status_code
        == 200
    )
    assert read_preferences(member.pk)["enable_avatar"] == "false"
    assert read_preferences(admin.pk)["enable_avatar"] == "true"
    another, another_session = browser(member)
    assert another_session["cache_identity"] != second_session["cache_identity"]
    another.credentials(HTTP_X_NASSAV_CONTEXT=second_session["cache_identity"])
    assert another.get("/nassav/api/setting").status_code == 409
    assert first.get("/nassav/api/setting").status_code == 200


def test_stale_tab_logout_does_not_log_out_current_cookie_account(managed):
    admin, member = managed
    _, old = browser(admin)
    current, snapshot = browser(member)
    current.credentials(
        HTTP_X_NASSAV_CONTEXT=old["cache_identity"],
        HTTP_X_CSRFTOKEN=current.cookies["csrftoken"].value,
    )
    response = current.post("/nassav/api/auth/logout", {}, format="json")
    assert response.status_code == 409
    assert (
        current.get("/nassav/api/auth/session").json()["data"]["user_id"] == member.pk
    )
    current.credentials(
        HTTP_X_NASSAV_CONTEXT=snapshot["cache_identity"],
        HTTP_X_CSRFTOKEN=current.cookies["csrftoken"].value,
    )
    assert current.post("/nassav/api/auth/logout", {}, format="json").status_code == 200
    assert not current.get("/nassav/api/auth/session").json()["data"]["authenticated"]


def test_managed_user_has_own_data_but_no_admin_global_cookie_or_task_controls(managed):
    _, member = managed
    client, _ = browser(member)
    for path, method in [
        ("/nassav/api/admin/users", "get"),
        ("/nassav/api/admin/source-credentials", "get"),
        ("/nassav/api/admin/resource-pools", "get"),
        ("/nassav/api/tasks/queue/status", "get"),
        ("/nassav/api/source/cookie", "get"),
        ("/nassav/api/resources/batch", "post"),
        ("/nassav/api/resource/PRIVATE-001", "delete"),
        (f"/nassav/api/tasks/jobs/{uuid4()}/pause", "post"),
    ]:
        assert getattr(client, method)(path).status_code == 403, path
    assert client.get("/nassav/api/me/source-credentials").status_code == 200
    assert client.get("/nassav/api/library/memberships").status_code == 200
    assert client.get("/nassav/api/my-operations").status_code == 200


def test_cross_owner_metadata_and_generic_cover_context_precede_bytes_or_etag(managed):
    admin, member = managed
    resource = AVResource.objects.create(
        avid="PRIVATE-001", source="jable", original_title="private-admin-title"
    )
    pool = ResourcePoolEntry.objects.create(
        canonical_avid=resource.avid, resource=resource, state="ready"
    )
    UserLibraryEntry.objects.create(
        user=admin, pool=pool, state="active", access_scope="public"
    )
    client, snapshot = browser(member)
    assert (
        client.get("/nassav/api/resource/metadata", {"avid": resource.avid}).status_code
        == 404
    )
    assert (
        client.get(
            "/nassav/api/resource/cover",
            {"avid": resource.avid},
            HTTP_IF_NONE_MATCH='"known"',
        ).status_code
        == 404
    )
    client.credentials()
    assert (
        client.get("/nassav/api/resource/cover", {"avid": resource.avid}).status_code
        == 409
    )
    assert (
        client.get(
            "/nassav/api/resource/cover",
            {"avid": resource.avid, "_context": snapshot["cache_identity"]},
            HTTP_IF_NONE_MATCH='"known"',
        ).status_code
        == 404
    )
    assert (
        client.get(
            "/nassav/api/resource/cover",
            {"avid": resource.avid, "_context": "another-login"},
            HTTP_IF_NONE_MATCH='"known"',
        ).status_code
        == 409
    )
    # An owned opaque handle path still performs its own authorization.
    assert (
        client.get("/nassav/api/library/entries/" + str(uuid4()) + "/image").status_code
        == 404
    )


def test_account_epoch_change_requires_new_context_without_silently_replaying_mutation(
    managed,
):
    _, member = managed
    client, old = browser(member)
    UserAccount.objects.filter(user=member).update(version=2)
    assert (
        client.put(
            "/nassav/api/setting", {"enable_avatar": "false"}, format="json"
        ).status_code
        == 409
    )
    current = client.get("/nassav/api/auth/session").json()["data"]
    assert current["cache_identity"] != old["cache_identity"]
    assert not UserPreferences.objects.filter(user=member).exists()


def test_stock_admin_cannot_bypass_last_admin_audit_or_password_commands(managed):
    admin, member = managed
    admin.is_staff = admin.is_superuser = True
    admin.save()
    for actor in (admin, member):
        client, _ = browser(actor)
        assert client.get("/admin/login/").status_code == 404
        response = client.post(
            f"/admin/auth/user/{admin.pk}/password/",
            {
                "password1": "Uncontrolled-password-123!",
                "password2": "Uncontrolled-password-123!",
            },
            HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value,
        )
        assert response.status_code in {302, 403, 404}
        admin.refresh_from_db()
        assert admin.check_password("Temporary-Managed-Admin-12!")


def test_multi_user_personal_response_and_conflicts_are_never_public_cacheable(managed):
    _, member = managed
    client, _ = browser(member)
    for response in [
        client.get("/nassav/api/setting"),
        client.get("/nassav/api/source/list"),
    ]:
        assert response["Cache-Control"] == "private, no-store"
        assert "Cookie" in response["Vary"]
    client.credentials(HTTP_X_NASSAV_CONTEXT="old-login")
    response = client.get("/nassav/api/setting")
    assert response.status_code == 409
    assert response["Cache-Control"] == "private, no-store"
    assert "Cookie" in response["Vary"]


@pytest.mark.django_db(transaction=True)
def test_websocket_context_handshake_private_groups_and_role_epoch_are_revalidated(
    managed, monkeypatch
):
    import asyncio
    from asgiref.sync import sync_to_async
    from channels.testing import WebsocketCommunicator
    from django_project.asgi import application
    from nassav.consumers import TaskConsumer, send_operation_hint

    admin, member = managed
    first, first_data = browser(admin)
    second, second_data = browser(member)

    async def quiet_status(self):
        return None

    monkeypatch.setattr(TaskConsumer, "_send_queue_status", quiet_status)

    def socket(client, identity):
        return WebsocketCommunicator(
            application,
            "/nassav/ws/tasks/",
            headers=[
                (b"host", b"localhost"),
                (b"origin", b"http://localhost"),
                (b"cookie", f"sessionid={client.session.session_key}".encode()),
            ],
            subprotocols=["nassav.tasks.v1", "nassav.context." + identity],
        )

    async def run():
        wrong = socket(second, first_data["cache_identity"])
        assert await wrong.connect() == (False, 4409)
        await wrong.disconnect()
        a = socket(first, first_data["cache_identity"])
        b = socket(second, second_data["cache_identity"])
        try:
            assert await a.connect() == (True, "nassav.tasks.v1")
            assert await b.connect() == (True, "nassav.tasks.v1")
            await sync_to_async(send_operation_hint)(
                admin.pk,
                {"operation_id": "owned-a", "version": 2, "cookie": "not-for-user"},
            )
            assert (await a.receive_json_from())["data"] == {
                "operation_id": "owned-a",
                "version": 2,
            }
            assert await b.receive_nothing(timeout=0.1)
            await sync_to_async(send_operation_hint)(
                member.pk, {"operation_id": "owned-b", "version": 3}
            )
            assert (await b.receive_json_from())["data"]["operation_id"] == "owned-b"
            assert await a.receive_nothing(timeout=0.1)
            await sync_to_async(UserAccount.objects.filter(user=member).update)(
                version=2
            )
            await b.send_json_to({"action": "get_queue_status"})
            assert (await b.receive_output())["code"] == 4409
        finally:
            await a.disconnect()
            await b.disconnect()

    asyncio.run(run())


def test_context_precondition_is_not_a_csrf_or_login_substitute(managed):
    _, member = managed
    client, snapshot = browser(member)
    client.credentials(HTTP_X_NASSAV_CONTEXT=snapshot["cache_identity"])
    assert (
        client.put(
            "/nassav/api/setting", {"enable_avatar": "false"}, format="json"
        ).status_code
        == 403
    )
    assert not UserPreferences.objects.filter(user=member).exists()
    client.logout()
    assert client.get("/nassav/api/setting").status_code == 401
