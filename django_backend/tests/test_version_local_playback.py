"""Actual decoded MP4 publication, authenticated ASGI Range and real Redis pins."""

import asyncio
import subprocess
from uuid import uuid4

import pytest
import redis
from asgiref.sync import sync_to_async
from channels.testing import HttpCommunicator
from django.test import Client
from django_project.asgi import application

from nassav import composition
from nassav.controlled_download import validate_video
from nassav.library_models import UserLibraryEntry
from nassav.resource_version_models import ResourceReadLease, ResourceVersion
from nassav.task_assets import AssetPromotion
from nassav.task_models import TaskAssetTarget
from nassav.playback import records, progress
from nassav.playback.local_files import submit_local
from nassav.playback.local_gateway import LocalPlaybackGateway
from nassav.playback.redis_state import RedisPlaybackCapacity
from nassav.playback.policy import PlaybackGatewayError
from nassav.playback.continuations import list_continuations
from nassav.http.playback_local_media import local_url
from test_version_publication import (
    environment as environment,
    context,
    runtime,
    operation,
    claim,
    publish,
    staged_cover,
)
from test_session_lifecycle_contracts import isolated_redis as _isolated_redis

local_redis = _isolated_redis
pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def close_thread_database_connections():
    yield
    from django.db import connections

    asyncio.run(sync_to_async(connections.close_all)())


@pytest.fixture
def clip(environment, settings):
    users, vault, roots = environment
    settings.SHARED_LIBRARY_ENABLED = True
    settings.SOURCE_CREDENTIALS_ENABLED = (
        False  # Local playback needs no source or keyring.
    )
    settings.PLAYBACK_ENABLED = True
    settings.NASSAV_OPERATOR_USERNAME = users[0].username
    for kind, root in roots.items():
        setattr(settings, f"{kind.upper()}_DIR", root)
    vault.write(
        users[0].pk,
        "jable",
        {
            "expected_version": 0,
            "cookie": "account_session=fixture-a",
            "user_agent": "fixture-UA",
        },
    )
    ctx = context(vault, users[0])
    tasks, publication, operations, assets = runtime(ctx, roots)
    op = operation(users[0], ctx, operations)
    token = claim(tasks, op)
    version = publication.prepare(token)
    publish(
        assets,
        publication,
        token,
        version,
        staged_cover(assets, token),
        title="private clip",
    )
    tasks.finish(token, "succeeded")
    operations.project(users[0].pk, op["operation_id"])
    op = operation(users[0], ctx, operations, action="download", kind="download")
    token = claim(tasks, op)
    version = publication.prepare(token)

    def write(path):
        subprocess.run(
            [
                "ffmpeg",
                "-nostdin",
                "-v",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "color=c=red:s=160x90:r=25:d=0.2",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-an",
                "-movflags",
                "+faststart",
                str(path),
            ],
            check=True,
            capture_output=True,
            timeout=10,
        )
        return True

    artifact = assets.stage(
        token,
        "video",
        "download/clip.mp4",
        "video",
        write,
        validate=lambda path: validate_video(
            path, 0.2, lambda: tasks.check(token), lambda _: None
        ),
    )
    target = publication.target(version, "video.mp4")
    row = assets.commit(
        token,
        [AssetPromotion(artifact, target)],
        lambda: publication.publish(
            token, version, {"avid": "PUB-001", "source_title": "video snapshot"}
        ),
    )
    tasks.finish(token, "succeeded")
    operations.project(users[0].pk, op["operation_id"])
    client = Client()
    client.force_login(users[0])
    return users, client, row, roots["video"] / target


def session(clip):
    users, client, version, _ = clip
    return submit_local(
        composition.build_local_video_locator(user_id=users[0].pk),
        records,
        users[0].pk,
        client.session.session_key,
        version.pool.canonical_avid,
        uuid4(),
    )


def test_local_version_session_is_fixed_and_pointer_race_rejects_wrong_grant(clip):
    users, client, version, path = clip
    locator = composition.build_local_video_locator(user_id=users[0].pk)
    descriptor = locator.identity("PUB-001")
    row = session(clip)
    assert row.library_grant["version_id"] == str(version.pk)
    assert row.descriptor["sha256"] == version.media_identity
    assert records.snapshot(row)["media_type"] == "mp4"
    assert str(path) not in str(records.snapshot(row))
    newer = ResourceVersion.objects.create(
        pool=version.pool,
        pool_generation=1,
        kind="video",
        source_name="jable",
        owner=users[0],
        access_scope=version.access_scope,
        context_revision="new-fixture",
        state="ready",
        published_at=version.published_at,
    )
    UserLibraryEntry.objects.filter(user=users[0]).update(video_version=newer)
    with pytest.raises(records.PlaybackStopped):
        records.submit(
            users[0].pk,
            client.session.session_key,
            "PUB-001",
            uuid4(),
            mode="local",
            descriptor=descriptor,
        )
    fixed = composition.build_local_video_locator(session=row)
    opened = fixed.open("PUB-001", row.descriptor)
    assert opened.read(0, 12) == path.read_bytes()[:12]
    opened.close()


def test_read_pin_can_drain_after_release_but_downlist_rejects(clip):
    users, client, version, _ = clip
    row = session(clip)
    reading = composition.build_playback_version_read(row, client.session.session_key)
    reading.check()
    assert ResourceReadLease.objects.get().version_id == version.pk
    from nassav.account_policy import can_read_playback

    entry = UserLibraryEntry.objects.get(user=users[0])
    composition.build_library_membership().release(
        users[0].pk, entry.pk, expected_version=entry.version
    )
    assert can_read_playback(users[0], row)
    reading.check()
    version.pool.is_available = False
    version.pool.save()
    assert not can_read_playback(users[0], row)
    from nassav.resource_reads import ReadLeaseNotFound

    with pytest.raises(ReadLeaseNotFound):
        reading.check()
    reading.close()
    assert not ResourceReadLease.objects.filter(state="active").exists()


@pytest.mark.parametrize("damage", ["marker", "replace", "symlink", "parent_symlink"])
def test_fixed_video_rejects_unowned_or_changed_files(clip, tmp_path, damage):
    _, _, version, path = clip
    row = session(clip)
    locator = composition.build_local_video_locator(session=row)
    if damage == "marker":
        TaskAssetTarget.objects.filter(
            root="video", relative_path=version.manifest[0]["path"]
        ).update(marker=uuid4())
    elif damage == "replace":
        data = path.read_bytes()
        path.write_bytes(b"x" + data[1:])
    elif damage == "symlink":
        other = tmp_path / "outside.mp4"
        other.write_bytes(path.read_bytes())
        path.unlink()
        path.symlink_to(other)
    else:
        moved = path.parent.with_name("moved")
        path.parent.rename(moved)
        path.parent.symlink_to(moved, target_is_directory=True)
    with pytest.raises(PlaybackGatewayError):
        locator.open("PUB-001", row.descriptor)


def test_continuation_uses_own_title_and_current_video_identity(clip):
    users, _, version, _ = clip
    row = session(clip)
    records.PlaybackSession.objects.filter(pk=row.pk).update(state="ready")
    from nassav.playback.models import PlaybackProgress

    PlaybackProgress.objects.create(
        user=users[0],
        avid="PUB-001",
        source="jable",
        media_kind="local",
        media_key=progress.media_key(row),
        position_seconds=30,
        duration_seconds=300,
    )
    result = list_continuations(
        users[0].pk,
        limit=6,
        locator=composition.build_local_video_locator(user_id=users[0].pk),
    )
    assert result[0]["source_title"] == "private clip"
    assert not list_continuations(
        users[1].pk,
        limit=6,
        locator=composition.build_local_video_locator(user_id=users[1].pk),
    )
    UserLibraryEntry.objects.filter(user=users[0]).update(video_version=None)
    assert not list_continuations(
        users[0].pk,
        limit=6,
        locator=composition.build_local_video_locator(user_id=users[0].pk),
    )


def test_private_mp4_asgi_range_head_owner_and_cleanup_with_real_redis(
    clip, monkeypatch, local_redis
):
    users, client, version, path = clip
    row = session(clip)
    socket = local_redis.connection_pool.connection_kwargs["path"]
    monkeypatch.setattr(
        composition,
        "build_local_playback_gateway",
        lambda: LocalPlaybackGateway(
            RedisPlaybackCapacity(
                redis.Redis(unix_socket_path=socket, socket_timeout=1)
            )
        ),
    )
    cookie = f"sessionid={client.session.session_key}".encode()
    other_login = Client()
    other_login.force_login(users[0])
    unrelated = Client()
    unrelated.force_login(users[1])

    async def fetch(method="GET", login=cookie, range_value=None):
        headers = [(b"host", b"localhost"), (b"cookie", login)]
        if range_value:
            headers.append((b"range", range_value.encode()))
        communicator = HttpCommunicator(
            application, method, local_url(row), headers=headers
        )
        await communicator.send_input({"type": "http.request", "body": b""})
        response = await communicator.receive_output(5)
        body = b""
        while True:
            event = await communicator.receive_output(5)
            body += event.get("body", b"")
            if not event.get("more_body", False):
                break
        await communicator.wait(5)
        return response["status"], body

    async def run():
        assert await fetch(range_value="bytes=5-14") == (206, path.read_bytes()[5:15])
        assert await fetch(method="HEAD") == (200, b"")
        assert (
            await fetch(login=f"sessionid={other_login.session.session_key}".encode())
        )[0] == 404
        assert (
            await fetch(login=f"sessionid={unrelated.session.session_key}".encode())
        )[0] == 401

    asyncio.run(run())
    assert not ResourceReadLease.objects.filter(state="active").exists()
    assert (
        ResourceReadLease.objects.filter(version=version, state="released").count() == 2
    )
    assert not local_redis.keys("nassav:playback:capacity:*")


def test_closed_pin_does_not_reopen_and_renewal_keeps_absolute_deadline(
    clip, monkeypatch
):
    users, client, _, _ = clip
    row = session(clip)
    reading = composition.build_playback_version_read(row, client.session.session_key)
    reading.check()
    first = ResourceReadLease.objects.get()
    reading.renewed_at -= 21
    reading.check()
    renewed = ResourceReadLease.objects.get()
    assert renewed.revision == first.revision + 1
    assert renewed.absolute_expires_at == first.absolute_expires_at
    reading.close()
    reading.close()
    with pytest.raises(PlaybackGatewayError, match="version_read_closed"):
        reading.check()
    assert ResourceReadLease.objects.count() == 1


def test_batched_continuation_identities_do_not_query_per_media(
    clip, django_assert_num_queries
):
    users, _, version, _ = clip
    locator = composition.build_local_video_locator(user_id=users[0].pk)
    with django_assert_num_queries(4):
        identities = locator.identities({"PUB-001"})
    assert identities["PUB-001"]["version_id"] == str(version.pk)


def test_versioned_http_submission_never_calls_source_and_status_uses_fixed_version(
    clip, monkeypatch, settings
):
    users, client, version, _ = clip
    from unittest.mock import Mock
    from nassav.tasks import playback_prepare_task

    settings.SOURCE_CREDENTIALS_ENABLED = True
    monkeypatch.setattr(
        composition,
        "build_credential_records",
        Mock(side_effect=AssertionError("local playback must not load credentials")),
    )
    dispatch = Mock()
    monkeypatch.setattr(playback_prepare_task, "apply_async", dispatch)
    command = {"mode": "local", "request_id": str(uuid4())}
    url = "/nassav/api/resources/PUB-001/playback-sessions"
    first = client.post(url, command, content_type="application/json")
    assert first.status_code == 202
    assert (
        client.post(url, command, content_type="application/json").json()["data"]
        == first.json()["data"]
    )
    row = records.PlaybackSession.objects.get(pk=first.json()["data"]["session_id"])
    assert row.library_grant["version_id"] == str(version.pk)
    status = client.get(f"/nassav/api/playback-sessions/{row.pk}")
    assert status.status_code == 200 and status.json()["data"]["media_url"]
    dispatch.assert_not_called()


def test_private_version_remains_static_when_credential_revoked_but_role_epoch_rejects(
    clip,
):
    users, _, version, _ = clip
    row = session(clip)
    from nassav.account_policy import can_read_playback
    from nassav.credential_models import SourceCredential
    from nassav.account_models import UserAccount

    SourceCredential.objects.filter(owner=users[0]).update(state="revoked")
    assert can_read_playback(users[0], row)
    UserAccount.objects.filter(user=users[0]).update(version=2)
    assert not can_read_playback(users[0], row)
    from nassav.resource_reads import ReadLeaseNotFound

    with pytest.raises(ReadLeaseNotFound):
        composition.build_playback_version_read(
            row, clip[1].session.session_key
        ).check()


def test_version_stream_disconnect_releases_fd_pin_and_redis_capacity(
    clip, monkeypatch, local_redis
):
    from threading import Event

    users, client, _, _ = clip
    row = session(clip)
    socket = local_redis.connection_pool.connection_kwargs["path"]
    monkeypatch.setattr(
        composition,
        "build_local_playback_gateway",
        lambda: LocalPlaybackGateway(
            RedisPlaybackCapacity(
                redis.Redis(unix_socket_path=socket, socket_timeout=1)
            )
        ),
    )
    original_builder = composition.build_local_video_locator
    opened = []
    started, allow_read = Event(), Event()

    def locator_builder(**kwargs):
        locator = original_builder(**kwargs)
        original_open = locator.open

        def open_video(avid, expected):
            video = original_open(avid, expected)
            original_read = video.read

            def blocked_read(offset, size):
                started.set()
                if not allow_read.wait(timeout=5):
                    raise RuntimeError("Test read release timed out")
                return original_read(offset, size)

            video.read = blocked_read
            opened.append(video)
            return video

        locator.open = open_video
        return locator

    monkeypatch.setattr(composition, "build_local_video_locator", locator_builder)

    async def run():
        communicator = HttpCommunicator(
            application,
            "GET",
            local_url(row),
            headers=[
                (b"host", b"localhost"),
                (b"cookie", f"sessionid={client.session.session_key}".encode()),
            ],
        )
        await communicator.send_input({"type": "http.request", "body": b""})
        response = await communicator.receive_output(5)
        assert response["status"] == 200
        assert await asyncio.to_thread(started.wait, 3)
        await communicator.send_input({"type": "http.disconnect"})
        allow_read.set()
        await communicator.wait(5)

    try:
        asyncio.run(run())
    finally:
        allow_read.set()
    assert opened and all(video.fd is None for video in opened)
    assert not ResourceReadLease.objects.filter(state="active").exists()
    assert ResourceReadLease.objects.filter(state="released").count() == 1
    assert not local_redis.keys("nassav:playback:capacity:*")


def test_removing_application_role_does_not_turn_version_grant_into_legacy_access(clip):
    from nassav.account_models import UserAccount
    from nassav.account_policy import can_read_playback

    users, _, _, _ = clip
    row = session(clip)
    UserAccount.objects.filter(user=users[0]).delete()
    assert not can_read_playback(users[0], row)
