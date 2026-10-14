"""HTTP authorization before lookup/media/conditional responses; login stays gated."""

import re
from uuid import uuid4
from types import SimpleNamespace

import pytest
from rest_framework.test import APIClient
from nassav.account_models import UserAccount
from nassav.account_policy import permit_business_view, ADMIN_VIEWS, is_app_admin
from nassav.library_models import ResourcePoolEntry, UserLibraryEntry
from nassav.models import AVResource
from nassav.urls import urlpatterns


@pytest.mark.django_db
def test_all_registered_api_views_reject_non_operator_even_with_django_admin_flags(
    django_user_model,
):
    user = django_user_model.objects.create_user(
        username="not-operator", is_staff=True, is_superuser=True
    )
    UserAccount.objects.create(user=user, role="admin")
    client = APIClient()
    client.force_authenticate(user)
    checked = 0
    for pattern in urlpatterns:
        if not getattr(pattern.callback, "cls", None):
            continue
        route = str(pattern.pattern)
        route = re.sub(r"<uuid:[^>]+>", str(uuid4()), route)
        route = re.sub(r"<int:[^>]+>", "1", route)
        route = re.sub(r"<str:[^>]+>", "TEST-001", route)
        assert client.get("/nassav/" + route).status_code == 403, route
        checked += 1
    assert checked > 50


@pytest.mark.django_db
def test_managed_operator_user_cannot_reach_legacy_global_mutations(operator_user):
    UserAccount.objects.create(user=operator_user, role="user")
    client = APIClient()
    client.force_authenticate(operator_user)
    for path, method in [
        ("/nassav/api/resource/TEST-001", "delete"),
        ("/nassav/api/resources/batch", "post"),
        ("/nassav/api/downloads/TEST-001", "post"),
        ("/nassav/api/downloads/TEST-001", "delete"),
        ("/nassav/api/source/cookie", "get"),
        ("/nassav/api/tasks/queue/status", "get"),
        ("/nassav/api/admin/users", "get"),
    ]:
        assert getattr(client, method)(path).status_code == 403
    for name in ADMIN_VIEWS:
        assert not permit_business_view(
            SimpleNamespace(user=operator_user, method="POST"), type(name, (), {})()
        )


@pytest.mark.django_db
def test_private_formal_metadata_and_cover_are_not_authorized_by_etag_or_id(
    operator_user, django_user_model
):
    UserAccount.objects.create(user=operator_user)
    other = django_user_model.objects.create_user(username="owner-b")
    resource = AVResource.objects.create(avid="PRIVATE-ACC", source="jable")
    pool = ResourcePoolEntry.objects.create(
        canonical_avid=resource.avid, resource=resource, state="ready"
    )
    UserLibraryEntry.objects.create(
        user=other, pool=pool, state="active", access_scope="public"
    )
    client = APIClient()
    client.force_authenticate(operator_user)
    for url in [
        f"/nassav/api/resource/metadata?avid={resource.avid}",
        f"/nassav/api/resource/{resource.avid}/preview",
        f"/nassav/api/resource/cover?avid={resource.avid}",
    ]:
        assert client.get(url, HTTP_IF_NONE_MATCH='"known"').status_code == 404
    UserLibraryEntry.objects.create(
        user=operator_user, pool=pool, state="active", access_scope="public"
    )
    assert (
        client.get(f"/nassav/api/resource/metadata?avid={resource.avid}").status_code
        == 200
    )
    response = client.get("/nassav/api/resources")
    assert response.status_code == 200
    assert len(response.json()["data"]) == 1
    assert not permit_business_view(
        SimpleNamespace(user=operator_user), type("UnregisteredView", (), {})()
    )


@pytest.mark.django_db
def test_django_staff_cannot_get_new_admin_api_and_non_operator_login_stays_closed(
    operator_user, django_user_model, client
):
    operator_user.is_staff = operator_user.is_superuser = True
    operator_user.save()
    api = APIClient()
    api.force_authenticate(operator_user)
    assert api.get("/nassav/api/admin/users").status_code == 403
    user = django_user_model.objects.create_user(
        username="new-admin", password="a-valid-admin-test-password"
    )
    UserAccount.objects.create(user=user, role="admin")
    assert is_app_admin(user)
    assert (
        client.post(
            "/nassav/api/auth/login",
            {"username": user.username, "password": "a-valid-admin-test-password"},
            content_type="application/json",
        ).status_code
        == 401
    )


@pytest.mark.django_db(transaction=True)
def test_managed_user_socket_receives_only_owned_safe_hints(operator_user, client):
    import asyncio
    from asgiref.sync import sync_to_async
    from channels.testing import WebsocketCommunicator
    from django_project.asgi import application
    from nassav.consumers import send_task_update
    from nassav.composition import build_task_records

    UserAccount.objects.create(user=operator_user, role="user")
    client.force_login(operator_user)
    headers = [
        (b"host", b"localhost"),
        (b"origin", b"http://localhost"),
        (b"cookie", f"sessionid={client.session.session_key}".encode()),
    ]
    own, _ = build_task_records().create(
        "scrape", "WS-OWN", action="add", owner_id=operator_user.pk
    )

    async def run():
        communicator = WebsocketCommunicator(
            application, "/nassav/ws/tasks/", headers=headers
        )
        assert (await communicator.connect())[0]
        await sync_to_async(send_task_update)(
            "progress_update", {"avid": "OTHER", "cookie": "not-for-client"}
        )
        assert await communicator.receive_nothing(timeout=0.1)
        await sync_to_async(send_task_update)(
            "task_job_update",
            {
                "job_id": own["job_id"],
                "version": 2,
                "job_type": "scrape",
                "cookie": "not-for-client",
                "private_path": "hidden",
            },
        )
        event = await communicator.receive_json_from()
        assert event["data"] == {
            "job_id": own["job_id"],
            "version": 2,
            "job_type": "scrape",
        }
        await communicator.send_json_to({"action": "get_queue_status"})
        assert (await communicator.receive_json_from())["type"] == "error"
        await communicator.disconnect()

    asyncio.run(run())


@pytest.mark.django_db
def test_external_search_and_recommendation_inventory_use_own_pending_membership(
    operator_user, django_user_model
):
    from nassav.external_search import project_library_presence
    from nassav.recommendation.data_access import DjangoCandidateInventory
    from nassav.composition import build_library_membership

    UserAccount.objects.create(user=operator_user)
    other = django_user_model.objects.create_user(username="remote-library-owner")
    resource = AVResource.objects.create(avid="SHARED-REMOTE")
    pool = ResourcePoolEntry.objects.create(
        canonical_avid=resource.avid, resource=resource, state="ready"
    )
    UserLibraryEntry.objects.create(
        user=other, pool=pool, state="active", access_scope="public"
    )
    items = [{"avid": resource.avid}, {"avid": "NOT-YET-SCRAPED"}]
    assert not any(
        item["in_library"]
        for item in project_library_presence(items, user_id=operator_user.pk)
    )
    build_library_membership().attach(
        operator_user.pk, "NOT-YET-SCRAPED", source="jable", access_scope="public"
    )
    assert project_library_presence(items, user_id=operator_user.pk)[1]["in_library"]
    assert DjangoCandidateInventory(user_id=operator_user.pk).existing(
        {resource.avid, "NOT-YET-SCRAPED"}
    ) == {"NOT-YET-SCRAPED"}


@pytest.mark.django_db
def test_non_operator_media_range_head_cannot_bypass_login_gate(
    django_user_model, client, settings
):
    settings.PLAYBACK_ENABLED = True
    user = django_user_model.objects.create_user(
        username="media-other", is_staff=True, is_superuser=True
    )
    UserAccount.objects.create(user=user, role="admin")
    client.force_login(user)
    session_id = uuid4()
    paths = [
        f"/nassav/api/playback-sessions/{session_id}/file",
        f"/nassav/api/playback-sessions/{session_id}/manifest/unknown",
        f"/nassav/api/playback-sessions/{session_id}/assets/unknown",
    ]
    for path in paths:
        for method in [client.get, client.head]:
            assert (
                method(
                    path, HTTP_RANGE="bytes=0-10", HTTP_IF_NONE_MATCH='"known"'
                ).status_code
                == 401
            )


@pytest.mark.django_db
def test_managed_user_cannot_read_other_legacy_scrape_snapshot_with_stolen_token(
    operator_user, django_user_model
):
    from nassav.composition import build_task_records
    from nassav.scrape_jobs import job_token

    UserAccount.objects.create(user=operator_user)
    other = django_user_model.objects.create_user(username="scrape-other")
    job, _ = build_task_records().create(
        "scrape", "PRIVATE-JOB", action="add", owner_id=other.pk
    )
    client = APIClient()
    client.force_authenticate(operator_user)
    response = client.get(
        f"/nassav/api/resource/jobs/{job['task_id']}",
        HTTP_X_RESOURCE_JOB_TOKEN=job_token(job["task_id"]),
    )
    assert response.status_code == 404


@pytest.mark.django_db
def test_admin_work_summary_does_not_grant_private_resource_titles(
    operator_user, django_user_model
):
    from nassav.admin_presentation import work_snapshot

    UserAccount.objects.create(user=operator_user, role="admin")
    other = django_user_model.objects.create_user(username="private-work-owner")
    resource = AVResource.objects.create(
        avid="PRIVATE-TITLE", original_title="private title"
    )
    pool = ResourcePoolEntry.objects.create(
        canonical_avid=resource.avid, resource=resource, state="ready"
    )
    UserLibraryEntry.objects.create(
        user=other,
        pool=pool,
        state="active",
        access_scope=f"legacy:operator:{other.pk}",
    )
    snapshot = {
        "avid": resource.avid,
        "owner_id": other.pk,
        "resource": {"avid": resource.avid, "original_title": resource.original_title},
        "resource_avid": resource.avid,
        "error_code": "SOURCE_ERROR",
        "message": "signed upstream URL",
    }
    safe = work_snapshot(snapshot, operator_user)
    assert safe["resource"] == {"avid": resource.avid} and safe["resource_avid"] is None
    assert "signed upstream URL" not in safe["message"]
