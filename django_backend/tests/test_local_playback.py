import asyncio
import os
from contextlib import asynccontextmanager
from unittest.mock import Mock
from uuid import uuid4

import pytest
from channels.testing import HttpCommunicator
from django.test import Client
from django_project.asgi import application
from nassav import composition
from nassav.playback import records
from nassav.playback.local_files import DjangoLocalVideoLocator, submit_local
from nassav.playback.local_gateway import LocalPlaybackGateway
from nassav.playback.policy import PlaybackGatewayError
from nassav.playback.redis_state import CapacityLease, RedisPlaybackCapacity
from nassav.http.playback_local_media import local_url
from test_session_lifecycle_contracts import isolated_redis as _isolated_redis

local_redis = _isolated_redis


@pytest.fixture(autouse=True)
def close_thread_database_connections():
    yield
    # Pure async gateway tests use the shared sync_to_async thread outside an
    # HTTP request; request_finished cannot close that test-owned connection.
    from asgiref.sync import sync_to_async
    from django.db import connections

    asyncio.run(sync_to_async(connections.close_all)())


class Capacity:
    def __init__(self):
        self.active = 0
        self.client = Mock()

    @asynccontextmanager
    async def slot(self, session_id):
        self.active += 1
        released = False

        async def release():
            nonlocal released
            if not released:
                released = True
                self.active -= 1

        try:
            yield CapacityLease(lambda: None, release)
        finally:
            await release()


@pytest.fixture
def local_video(tmp_path, settings, resource_factory):
    settings.PLAYBACK_ENABLED = True
    settings.VIDEO_DIR = tmp_path / "resource/video"
    settings.COVER_DIR = tmp_path / "resource/cover"
    settings.VIDEO_DIR.mkdir(parents=True)
    settings.COVER_DIR.mkdir()
    resource = resource_factory(avid="LOCAL-1", source="Jable", file_exists=True)
    path = settings.VIDEO_DIR / "LOCAL-1.mp4"
    path.write_bytes(bytes(range(256)) * 1024)
    return resource, path, composition.build_local_video_locator()


@pytest.mark.django_db
def test_local_submission_has_no_worker_proxy_or_uri_registry(
    local_video, operator_user, monkeypatch
):
    from nassav.tasks import playback_prepare_task

    dispatch = Mock()
    monkeypatch.setattr(playback_prepare_task, "apply_async", dispatch)
    monkeypatch.setattr(
        composition,
        "build_playback_resolver",
        Mock(side_effect=AssertionError("source")),
    )
    monkeypatch.setattr(
        composition,
        "build_playback_registry",
        Mock(side_effect=AssertionError("URI registry")),
    )
    resource, path, locator = local_video
    client = Client()
    client.force_login(operator_user)
    command = str(uuid4())
    url = f"/nassav/api/resources/{resource.avid}/playback-sessions"
    response = client.post(
        url, {"request_id": command, "mode": "local"}, content_type="application/json"
    )
    assert response.status_code == 202
    row = records.PlaybackSession.objects.get(pk=response.json()["data"]["session_id"])
    assert row.state == "ready" and row.media_kind == "local"
    assert records.claim(row.pk) is None
    status = client.get(f"/nassav/api/playback-sessions/{row.pk}").json()["data"]
    assert status["media_type"] == "mp4" and status["mode"] == "local"
    assert "manifest_url" not in status and status["allowed_actions"] == ["close"]
    assert str(path) not in str(status) and "fingerprint" not in str(status)
    assert client.post(
        url, {"request_id": command, "mode": "local"}, content_type="application/json"
    ).json()["data"]["session_id"] == str(row.pk)
    assert (
        client.post(
            url,
            {"request_id": command, "mode": "source"},
            content_type="application/json",
        ).status_code
        == 400
    )
    assert (
        client.post(
            f"/nassav/api/playback-sessions/{row.pk}/refresh",
            {"request_id": str(uuid4()), "expected_version": row.version},
            content_type="application/json",
        ).status_code
        == 409
    )
    records.recover(dispatch)
    dispatch.assert_not_called()
    path.unlink()
    failed = client.get(f"/nassav/api/playback-sessions/{row.pk}").json()["data"]
    assert failed["state"] == "failed" and failed["error_code"] == "local_media_removed"


@pytest.mark.django_db
def test_locator_rejects_private_paths_links_and_same_size_replacements(
    local_video, operator_user, tmp_path
):
    resource, path, locator = local_video
    with pytest.raises(PlaybackGatewayError):
        locator.path("../video/.tasks/job")
    row = submit_local(
        locator, records, operator_user.pk, "login", resource.avid, uuid4()
    )
    opened = locator.open(resource.avid, row.descriptor)
    replacement = path.with_suffix(".new")
    replacement.write_bytes(b"X" * path.stat().st_size)
    replacement.replace(path)
    assert opened.read(0, 4) == bytes(range(4))
    with pytest.raises(PlaybackGatewayError, match="media_identity_changed"):
        locator.open(resource.avid, row.descriptor)
    opened.close()
    path.unlink()
    external = tmp_path / "outside.mp4"
    external.write_bytes(b"outside")
    path.symlink_to(external)
    with pytest.raises(PlaybackGatewayError, match="local_video_rejected"):
        locator.identity(resource.avid)
    path.unlink()
    path.write_bytes(b"new")
    alias = tmp_path / "video-alias"
    alias.symlink_to(locator.root, target_is_directory=True)
    assert (
        DjangoLocalVideoLocator(alias, locator.cover_root).identity(resource.avid)[
            "fingerprint"
        ][2]
        == 3
    )


@pytest.mark.django_db
def test_locator_publication_marker_and_pending_log(local_video, operator_user):
    from nassav.task_models import TaskAssetTarget, TaskArtifact
    from nassav.task_records import DjangoTaskRecords

    resource, path, locator = local_video
    expected = locator.identity(resource.avid)
    target = TaskAssetTarget.objects.create(root="video", relative_path=path.name)
    with pytest.raises(PlaybackGatewayError, match="media_identity_changed"):
        locator.check(resource.avid, expected)
    current = locator.identity(resource.avid)
    target.marker = uuid4()
    target.save()
    with pytest.raises(PlaybackGatewayError, match="media_identity_changed"):
        locator.check(resource.avid, current)
    # A crash between rename and commit must not publish an uncommitted video.
    job, _ = DjangoTaskRecords().create(
        "download", resource.avid, owner_id=operator_user.pk, action="download"
    )
    TaskArtifact.objects.create(
        job_id=job["job_id"],
        root="video",
        relative_path=".tasks/job/video",
        target_path=path.name,
        state="promoting",
    )
    with pytest.raises(PlaybackGatewayError, match="local_publication_pending"):
        locator.identity(resource.avid)


@pytest.mark.django_db(transaction=True)
def test_asgi_local_ranges_authorization_head_and_close(
    local_video, operator_user, monkeypatch
):
    resource, path, locator = local_video
    client = Client()
    client.force_login(operator_user)
    row = submit_local(
        locator,
        records,
        operator_user.pk,
        client.session.session_key,
        resource.avid,
        uuid4(),
    )
    url = local_url(row)
    capacity = Capacity()
    monkeypatch.setattr(
        composition,
        "build_local_playback_gateway",
        lambda: LocalPlaybackGateway(capacity),
    )
    other = Client()
    other.force_login(operator_user)
    cookie = f"sessionid={client.session.session_key}".encode()

    async def fetch(
        method="GET", range_value=None, token=url, login=cookie, if_range=None
    ):
        headers = [(b"host", b"localhost")]
        if login:
            headers.append((b"cookie", login))
        if range_value:
            headers.append((b"range", range_value.encode()))
        if if_range:
            headers.append((b"if-range", if_range.encode()))
        communicator = HttpCommunicator(application, method, token, headers=headers)
        await communicator.send_input({"type": "http.request", "body": b""})
        response = await communicator.receive_output(5)
        response["body"] = b""
        while True:
            event = await communicator.receive_output(5)
            response["body"] += event.get("body", b"")
            if not event.get("more_body", False):
                break
        await communicator.wait(5)
        assert capacity.active == 0
        return response

    async def run():
        assert (await fetch(login=None))["status"] == 401
        assert (await fetch(login=f"sessionid={other.session.session_key}".encode()))[
            "status"
        ] == 404
        assert (await fetch(token=url.split("?")[0] + "?cap=bad"))["status"] == 403
        full = await fetch()
        assert full["status"] == 200 and full["body"] == path.read_bytes()
        headers = {key.lower(): value for key, value in full["headers"]}
        assert (
            headers[b"content-type"] == b"video/mp4"
            and headers[b"cache-control"] == b"no-store"
        )
        for requested, expected in [
            ("bytes=10-19", path.read_bytes()[10:20]),
            ("bytes=-7", path.read_bytes()[-7:]),
            ("bytes=262140-", path.read_bytes()[-4:]),
        ]:
            response = await fetch(range_value=requested)
            assert response["status"] == 206 and response["body"] == expected
        for invalid in [
            "bytes=300000-",
            "bytes=-0",
            "bytes=5-2",
            "bytes=0-1,5-6",
            "garbage",
        ]:
            response = await fetch(range_value=invalid)
            assert response["status"] == 416
            assert {key.lower(): value for key, value in response["headers"]}[
                b"content-range"
            ] == b"bytes */262144"
        assert (
            await fetch(range_value="bytes=0-4", if_range=headers[b"etag"].decode())
        )["status"] == 206
        assert (await fetch(range_value="bytes=0-4", if_range='"old"'))["status"] == 200
        head = await fetch(method="HEAD", range_value="bytes=0-4")
        assert head["status"] == 200 and not head["body"]
        assert {key.lower(): value for key, value in head["headers"]}[
            b"content-length"
        ] == b"262144"
        assert (await fetch(method="POST"))[
            "status"
        ] == 403  # CSRF middleware rejects unsafe requests first.

    asyncio.run(run())
    records.close(
        row.pk, operator_user.pk, client.session.session_key, row.version, uuid4()
    )
    assert asyncio.run(fetch())["status"] == 410


def test_gateway_revokes_idle_consumer_and_bounded_reads(tmp_path):
    from nassav.playback.local_files import LocalVideo

    path = tmp_path / "large.mp4"
    with path.open("wb") as file:
        file.truncate(128 * 1024 * 1024)
    video = LocalVideo(os.open(path, os.O_RDONLY))
    capacity = Capacity()
    valid = True

    async def check():
        if not valid:
            raise PlaybackGatewayError("session_closed", 410)

    async def opener():
        return video

    async def run():
        nonlocal valid
        async with LocalPlaybackGateway(capacity).open(
            "session",
            {"fingerprint": [0, 0, path.stat().st_size, 0, 0]},
            opener=opener,
            check=check,
        ) as result:
            assert result.headers["Content-Length"] == str(path.stat().st_size)
            assert len(await anext(result.body)) == 65536
            valid = False
            await asyncio.sleep(0.7)
            assert video.fd is None and capacity.active == 0
            with pytest.raises(PlaybackGatewayError):
                await anext(result.body)
        assert capacity.active == 0

    asyncio.run(run())


def test_gateway_cancel_during_open_closes_late_fd(tmp_path):
    from nassav.playback.local_files import LocalVideo

    path = tmp_path / "sample.mp4"
    path.write_bytes(b"sample")

    async def run():
        started, done = asyncio.Event(), asyncio.Event()
        capacity = Capacity()
        video = LocalVideo(os.open(path, os.O_RDONLY))

        async def opener():
            started.set()
            await done.wait()
            return video

        async def check():
            pass

        async def transfer():
            async with LocalPlaybackGateway(capacity).open(
                "sid", {"fingerprint": [0, 0, 6, 0, 0]}, opener=opener, check=check
            ):
                pass

        task = asyncio.create_task(transfer())
        await started.wait()
        task.cancel()
        task.cancel()
        done.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert video.fd is None and capacity.active == 0

    asyncio.run(run())


@pytest.mark.django_db(transaction=True)
def test_asgi_disconnect_returns_real_redis_capacity_and_fd(
    local_video, operator_user, monkeypatch, local_redis
):
    import time

    resource, path, locator = local_video
    client = Client()
    client.force_login(operator_user)
    key = client.session.session_key
    row = submit_local(locator, records, operator_user.pk, key, resource.avid, uuid4())
    redis_client = local_redis
    capacity = RedisPlaybackCapacity(redis_client)
    # Prevent closing the fixture's shared client; Redis capacity itself is real.
    original_close = redis_client.close
    monkeypatch.setattr(redis_client, "close", lambda: None)
    monkeypatch.setattr(
        composition,
        "build_local_playback_gateway",
        lambda: LocalPlaybackGateway(capacity),
    )
    opened = []
    original_open = locator.open

    def slow_open(avid, descriptor):
        video = original_open(avid, descriptor)
        opened.append(video)
        read = video.read

        def slow_read(offset, size):
            time.sleep(0.1)
            return read(offset, size)

        video.read = slow_read
        return video

    locator.open = slow_open
    monkeypatch.setattr(composition, "build_local_video_locator", lambda: locator)

    async def run():
        communicator = HttpCommunicator(
            application,
            "GET",
            local_url(row),
            headers=[(b"host", b"localhost"), (b"cookie", f"sessionid={key}".encode())],
        )
        await communicator.send_input({"type": "http.request", "body": b""})
        assert (await communicator.receive_output(5))["status"] == 200
        assert (await communicator.receive_output(5))["body"]
        assert (
            await asyncio.to_thread(
                redis_client.zcard, "nassav:playback:capacity:global"
            )
            == 1
        )
        await communicator.send_input({"type": "http.disconnect"})
        await communicator.wait(5)
        for _ in range(50):
            if (
                opened[0].fd is None
                and await asyncio.to_thread(
                    redis_client.zcard, "nassav:playback:capacity:global"
                )
                == 0
            ):
                break
            await asyncio.sleep(0.02)
        assert opened[0].fd is None
        assert (
            await asyncio.to_thread(
                redis_client.zcard, "nassav:playback:capacity:global"
            )
            == 0
        )
        assert (
            await asyncio.to_thread(
                redis_client.zcard, f"nassav:playback:capacity:{row.pk}"
            )
            == 0
        )

    try:
        asyncio.run(run())
    finally:
        original_close()


@pytest.mark.django_db
def test_resource_lock_timeout_preserves_stable_lock_and_allows_retry(local_video):
    import fcntl
    from nassav.resource_file_locks import resource_file_lock

    resource, _, locator = local_video
    lock_path = (
        locator.cover_root.parent / ".nassav-delete-locks" / f"{resource.avid}.lock"
    )
    lock_path.parent.mkdir(exist_ok=True)
    with lock_path.open("a+b") as holder:
        fcntl.flock(holder, fcntl.LOCK_EX)
        with pytest.raises(TimeoutError):
            with resource_file_lock(resource.avid, locator.cover_root, timeout=0.02):
                pass
        fcntl.flock(holder, fcntl.LOCK_UN)
    with resource_file_lock(resource.avid, locator.cover_root, timeout=0.02):
        pass
    assert lock_path.exists()


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("change", ["delete", "replace"])
def test_local_inflight_stops_after_real_delete_or_replacement(
    local_video, operator_user, change
):
    from asgiref.sync import sync_to_async
    from nassav.http.playback_local_media import check_local
    from nassav.resource_deletion import ResourceDeletionService

    resource, path, locator = local_video
    row = submit_local(
        locator, records, operator_user.pk, "login", resource.avid, uuid4()
    )
    capacity = Capacity()
    opened = []

    async def opener():
        video = await sync_to_async(locator.open)(resource.avid, row.descriptor)
        opened.append(video)
        return video

    async def check():
        await sync_to_async(check_local)(row, locator)

    async def run():
        async with LocalPlaybackGateway(capacity).open(
            row.pk, row.descriptor, opener=opener, check=check
        ) as response:
            await anext(response.body)
            if change == "delete":
                await sync_to_async(ResourceDeletionService().delete_video)(
                    resource.avid
                )
            else:
                replacement = path.with_suffix(".replacement")
                replacement.write_bytes(b"R" * path.stat().st_size)
                replacement.replace(path)
            await asyncio.sleep(0.7)
            assert opened[0].fd is None and capacity.active == 0
            with pytest.raises(PlaybackGatewayError):
                await anext(response.body)
        assert capacity.active == 0

    asyncio.run(run())
    row.refresh_from_db()
    assert row.state == "failed"


def test_local_idle_consumer_releases_fd_and_capacity(tmp_path):
    from nassav.playback.local_files import LocalVideo

    path = tmp_path / "idle.mp4"
    path.write_bytes(b"video")
    video = LocalVideo(os.open(path, os.O_RDONLY))
    capacity = Capacity()

    async def check():
        pass

    async def opener():
        return video

    async def run():
        async with LocalPlaybackGateway(capacity, idle_seconds=0.05).open(
            "sid", {"fingerprint": [0, 0, 5, 0, 0]}, opener=opener, check=check
        ):
            await asyncio.sleep(0.7)
            assert video.fd is None and capacity.active == 0

    asyncio.run(run())
