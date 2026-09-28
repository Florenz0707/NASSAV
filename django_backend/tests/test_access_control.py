"""P1 session, CSRF, and task-stream access regressions.

Run with DB_ENGINE=sqlite and the template config; test credentials and files are disposable.
"""

import asyncio

import pytest
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client
from rest_framework.test import APIClient

from django_project.asgi import application
from nassav import scrape_jobs, tasks
from nassav.models import AVResource


@pytest.mark.django_db
def test_anonymous_sensitive_routes_are_denied(resource_factory, settings, tmp_path):
    client = APIClient()
    avid = "P1-DENY-1"
    resource_factory(avid=avid)
    settings.COVER_DIR = tmp_path / "cover"
    settings.COVER_DIR.mkdir()
    cover = settings.COVER_DIR / f"{avid}.jpg"
    cover.write_bytes(b"test-cover")
    task_id = "00000000-0000-0000-0000-000000000001"
    cases = [
        client.get("/nassav/api/source/cookie"),
        client.put("/nassav/api/setting", {"color_mode": "light"}, format="json"),
        client.delete(f"/nassav/api/resource/{avid}"),
        client.post("/nassav/api/recommendations/reset", {}, format="json"),
        client.get("/nassav/api/tasks/queue/status"),
        client.get(
            f"/nassav/api/resource/jobs/{task_id}",
            HTTP_X_RESOURCE_JOB_TOKEN=scrape_jobs.job_token(task_id),
        ),
    ]
    assert [response.status_code for response in cases] == [401] * len(cases)
    assert AVResource.objects.filter(avid=avid).exists()
    assert cover.exists()


@pytest.mark.django_db
def test_only_configured_operator_can_use_business_api(operator_user, settings):
    client = APIClient()
    other = get_user_model().objects.create_user("other", password="test-only-password")
    client.force_login(other)
    assert client.get("/nassav/api/source/cookie").status_code == 403
    client.force_login(operator_user)
    assert client.get("/nassav/api/source/cookie").status_code == 200


@pytest.mark.django_db
def test_session_login_requires_csrf_and_protects_writes(operator_user):
    browser = Client(enforce_csrf_checks=True)
    session = browser.get("/nassav/api/auth/session")
    assert session.status_code == 200
    assert session.json()["data"]["authenticated"] is False
    assert settings.CSRF_COOKIE_NAME in browser.cookies
    credentials = {
        "username": operator_user.get_username(),
        "password": "p0-p1-test-only-password",
    }
    assert (
        browser.post(
            "/nassav/api/auth/login", credentials, content_type="application/json"
        ).status_code
        == 403
    )
    token = browser.cookies[settings.CSRF_COOKIE_NAME].value
    response = browser.post(
        "/nassav/api/auth/login",
        credentials,
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token,
    )
    assert response.status_code == 200
    assert (
        browser.get("/nassav/api/auth/session").json()["data"]["authenticated"] is True
    )
    assert (
        browser.put(
            "/nassav/api/setting",
            {"color_mode": "light"},
            content_type="application/json",
        ).status_code
        == 403
    )
    token = browser.cookies[settings.CSRF_COOKIE_NAME].value
    assert (
        browser.put(
            "/nassav/api/setting",
            {"color_mode": "light"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
        ).status_code
        == 200
    )
    assert browser.post("/nassav/api/auth/logout").status_code == 403
    assert (
        browser.post("/nassav/api/auth/logout", HTTP_X_CSRFTOKEN=token).status_code
        == 200
    )
    assert browser.get("/nassav/api/source/cookie").status_code == 401


@pytest.mark.django_db
def test_signed_job_snapshot_still_requires_session_and_token(api_client, monkeypatch):
    task_id = "00000000-0000-0000-0000-000000000002"
    monkeypatch.setattr(
        scrape_jobs,
        "get_resource_job",
        lambda task_id: {"task_id": task_id, "state": "running", "stage": "saving"},
    )
    path = f"/nassav/api/resource/jobs/{task_id}"
    assert api_client.get(path).status_code == 403
    assert (
        api_client.get(
            path, HTTP_X_RESOURCE_JOB_TOKEN=scrape_jobs.job_token(task_id)
        ).status_code
        == 200
    )


@pytest.mark.django_db(transaction=True)
def test_task_websocket_rejects_anonymous_and_cross_origin(monkeypatch, ws_headers):
    monkeypatch.setattr(tasks, "get_task_queue_status", lambda: {"active_tasks": []})

    async def run():
        denied_headers = [
            [(b"host", b"localhost"), (b"origin", b"http://localhost")],
            [
                (key, b"https://evil.example" if key == b"origin" else value)
                for key, value in ws_headers
            ],
            [(key, value) for key, value in ws_headers if key != b"origin"],
        ]
        for headers in denied_headers:
            communicator = WebsocketCommunicator(
                application, "/nassav/ws/tasks/", headers=headers
            )
            connected, _ = await communicator.connect()
            assert not connected
            await communicator.wait()
        communicator = WebsocketCommunicator(
            application, "/nassav/ws/tasks/", headers=ws_headers
        )
        connected, _ = await communicator.connect()
        assert connected
        assert (await communicator.receive_json_from())["type"] == "queue_status"
        await communicator.disconnect()

        proxy_headers = [
            (b"host", b"localhost:8443"),
            (b"origin", b"https://localhost:8443"),
            (b"x-forwarded-proto", b"https"),
            next((header for header in ws_headers if header[0] == b"cookie")),
        ]
        proxied = WebsocketCommunicator(
            application, "/nassav/ws/tasks/", headers=proxy_headers
        )
        connected, _ = await proxied.connect()
        assert connected
        assert (await proxied.receive_json_from())["type"] == "queue_status"
        await proxied.disconnect()

    asyncio.run(run())


@pytest.mark.django_db(transaction=True)
def test_revoked_session_cannot_receive_task_events(monkeypatch, ws_headers, client):
    monkeypatch.setattr(tasks, "get_task_queue_status", lambda: {"active_tasks": []})

    async def run():
        communicator = WebsocketCommunicator(
            application, "/nassav/ws/tasks/", headers=ws_headers
        )
        connected, _ = await communicator.connect()
        assert connected
        await communicator.receive_json_from()
        await asyncio.to_thread(client.logout)
        await get_channel_layer().group_send(
            "task_updates",
            {
                "type": "task_update",
                "update_type": "progress_update",
                "data": {"percent": 99},
            },
        )
        closing = await communicator.receive_output(timeout=1)
        assert closing["type"] == "websocket.close"
        assert closing["code"] == 4401
        await communicator.wait()

    asyncio.run(run())
