"""Scoped preparation/HTTP/real Redis with synthetic upstream transport, no account probes."""

import asyncio
from uuid import uuid4
from unittest.mock import Mock

import pytest
from asgiref.sync import sync_to_async
from channels.testing import HttpCommunicator
from django.test import Client
from django_project.asgi import application

from nassav import composition
from nassav.account_policy import can_read_playback
from nassav.credential_playback import binding_current
from nassav.credential_crypto import CredentialUnavailable
from nassav.library_models import UserLibraryEntry
from nassav.resource_version_models import ResourceReadLease, ResourceVersion
from nassav.models import ResourcePlaybackCache
from nassav.playback import records, progress
from nassav.playback.preparation import execute
from nassav.playback.contracts import PlaybackDescriptor
from nassav.playback.continuations import list_continuations
from nassav.playback.models import PlaybackProgress
from nassav.source.Jable import Jable
from nassav.scoped_source_context import CredentialSourceContext
from nassav.page_fetching.proxy_server import ProxySessionCapabilities
from nassav.http.playback_media import capability
from nassav.playback.redis_state import RedisPlaybackCapacity
from test_version_publication import (
    environment as environment,
    context,
    runtime,
    operation,
    claim,
    publish,
    staged_cover,
)
from test_playback_gateway import make_gateway, Response
from test_session_lifecycle_contracts import isolated_redis as _isolated_redis

playback_redis = _isolated_redis
pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def close_thread_database_connections():
    yield
    from django.db import connections

    asyncio.run(sync_to_async(connections.close_all)())


@pytest.fixture
def source_versions(environment, settings, monkeypatch):
    users, vault, roots = environment
    settings.SHARED_LIBRARY_ENABLED = settings.SOURCE_CREDENTIALS_ENABLED = (
        settings.PLAYBACK_ENABLED
    ) = True
    settings.NASSAV_OPERATOR_USERNAME = users[0].username
    settings.PROXY_ENABLED = False
    monkeypatch.setattr(composition, "build_credential_records", lambda: vault)
    entries, clients = [], []
    for user in users:
        vault.write(
            user.pk,
            "jable",
            {
                "expected_version": 0,
                "cookie": f"account_session=fixture-{user.pk}",
                "user_agent": f"fixture-UA-{user.pk}",
            },
        )
        ctx = context(vault, user)
        tasks, publication, operations, assets = runtime(ctx, roots)
        op = operation(user, ctx, operations)
        token = claim(tasks, op)
        version = publication.prepare(token)
        publish(
            assets,
            publication,
            token,
            version,
            staged_cover(assets, token),
            title=f"private title {user.pk}",
        )
        tasks.finish(token, "succeeded")
        operations.project(user.pk, op["operation_id"])
        entries.append(
            UserLibraryEntry.objects.select_related(
                "pool__resource", "current_version"
            ).get(user=user)
        )
        client = Client()
        client.force_login(user)
        clients.append(client)
    return users, vault, entries, clients


def submit(source_versions, index=0):
    users, _, entries, clients = source_versions
    auth = composition.build_playback_source_binding("PUB-001", user_id=users[index].pk)
    return records.submit(
        users[index].pk,
        clients[index].session.session_key,
        "PUB-001",
        uuid4(),
        source_auth=auth,
    )


def descriptor(row):
    return PlaybackDescriptor(
        "https://media.example/v.m3u8",
        "https://jable.tv/videos/pub-001/",
        f"fixture-UA-{row.user_id}",
        "jable",
        None,
        None,
    )


def test_source_grant_uses_frozen_own_reference_not_empty_canonical_or_other_owner(
    source_versions,
):
    users, vault, entries, _ = source_versions
    first, second = submit(source_versions), submit(source_versions, 1)
    assert first.source == second.source == "jable"
    assert first.library_grant["source_auth"] != second.library_grant["source_auth"]
    assert first.library_grant["version_id"] == str(entries[0].current_version.pk)
    assert not entries[0].pool.resource.source
    assert binding_current(
        first.library_grant["source_auth"],
        "jable",
        owner_id=users[0].pk,
        access_scope=first.library_grant["scope"],
    )
    assert not binding_current(
        first.library_grant["source_auth"],
        "jable",
        owner_id=users[1].pk,
        access_scope=first.library_grant["scope"],
    )
    with pytest.raises(records.PlaybackStopped):
        records.submit(
            users[1].pk,
            "other-login",
            "PUB-001",
            uuid4(),
            source_auth=first.library_grant["source_auth"],
        )
    assert ResourceVersion.objects.count() == 2


def test_changed_credentials_require_metadata_refresh_and_missing_key_fails_closed(
    source_versions, monkeypatch
):
    users, vault, entries, _ = source_versions
    vault.write(
        users[0].pk,
        "jable",
        {
            "expected_version": 1,
            "cookie": "account_session=new",
            "user_agent": "new-UA",
        },
    )
    with pytest.raises(PermissionError):
        composition.build_playback_source_binding("PUB-001", user_id=users[0].pk)

    def unavailable():
        raise CredentialUnavailable("Key missing")

    monkeypatch.setattr(composition, "build_credential_records", unavailable)
    with pytest.raises(CredentialUnavailable):
        composition.build_playback_source_binding("PUB-001", user_id=users[1].pk)


def test_default_resolver_selects_frozen_private_owner_and_keeps_sources_independent(
    source_versions, monkeypatch, settings
):
    users, vault, _, _ = source_versions
    rows = [submit(source_versions, index) for index in range(2)]
    settings.PROXY_ENABLED = True
    settings.PROXY_URL = "http://global-proxy.example:8080"
    settings.DOWNLOAD_PROXY_URL = "http://download-proxy.example:8081"
    made, calls, observed = [], [], []
    html = '<title>PUB-001 Private - Jable.TV</title><script>var hlsUrl = "https://media.example/v.m3u8";</script><section class="video-info"></section>'

    def factories(proxy, browser, save_cookie, **kwargs):
        calls.append((proxy, kwargs))

        def fresh():
            source = Jable(proxy=proxy)
            source.bind_credential_context(
                CredentialSourceContext(
                    lambda: vault,
                    "jable",
                    user_id=kwargs.get("user_id"),
                    credential_id=kwargs.get("credential_id"),
                    egress_profile="direct",
                    browser_context="fixture-v1",
                    capabilities=ProxySessionCapabilities(),
                )
            )

            def get_html(avid):
                observed.append(
                    (
                        kwargs.get("user_id"),
                        source.cookie,
                        source.credential_context.load_session().user_agent,
                    )
                )
                return html

            source.get_html = get_html
            made.append(source)
            return source

        return {"jable": fresh}

    monkeypatch.setattr(composition, "source_factories", factories)
    for row in rows:
        execute(row.pk, composition.build_playback_resolver(session_id=row.pk), records)
        row.refresh_from_db()
        assert row.state == "ready"
        assert row.descriptor["user_agent"] == f"fixture-UA-{row.user_id}"
    assert len(made) == 2 and made[0] is not made[1]
    assert all(proxy == settings.PROXY_URL for proxy, _ in calls)
    assert all(row.descriptor["route_profile"] for row in rows)
    assert observed == [
        (user.pk, f"account_session=fixture-{user.pk}", f"fixture-UA-{user.pk}")
        for user in users
    ]
    assert [args["user_id"] for _, args in calls if args.get("credential_id")] == [
        user.pk for user in users
    ]
    assert ResourcePlaybackCache.objects.count() == 2
    assert all(
        "account_session" not in str(item.payload)
        for item in ResourcePlaybackCache.objects.all()
    )


def test_revocation_stops_owned_preparation_and_late_cache_publication(source_versions):
    users, vault, _, _ = source_versions
    row = submit(source_versions)
    token = records.claim(row.pk)
    vault.write(
        users[0].pk,
        "jable",
        {"expected_version": 1},
        credential_id=row.library_grant["source_auth"]["credential_id"],
        revoke=True,
    )
    with pytest.raises(records.PlaybackStopped):
        records.ready(token, descriptor(row))
    callback = Mock()
    with pytest.raises(records.PlaybackStopped):
        records.publish(token, callback)
    callback.assert_not_called()
    row.refresh_from_db()
    assert row.state == "closed" and not row.descriptor
    assert not can_read_playback(users[0], row)


def test_source_ledger_scope_does_not_mix_and_continuation_requires_current_scope(
    source_versions,
):
    users, _, entries, _ = source_versions
    row = submit(source_versions)
    records.ready(records.claim(row.pk), descriptor(row))
    row.refresh_from_db()
    different = records.PlaybackSession(
        user=users[0],
        resource=row.resource,
        source=row.source,
        media_kind="source",
        library_grant={**row.library_grant, "scope": "public"},
    )
    assert progress.media_key(different) != progress.media_key(row)
    PlaybackProgress.objects.create(
        user=users[0],
        avid="PUB-001",
        source="jable",
        media_kind="source",
        media_key=progress.media_key(row),
        position_seconds=30,
        duration_seconds=300,
    )
    assert (
        list_continuations(
            users[0].pk, limit=6, locator=Mock(identities=lambda avids: {})
        )[0]["source_title"]
        == f"private title {users[0].pk}"
    )
    version = ResourceVersion.objects.create(
        pool=entries[0].pool,
        pool_generation=1,
        kind="metadata",
        source_name="jable",
        owner=users[0],
        access_scope=entries[0].access_scope,
        context_revision="new-credential-context",
        state="ready",
        published_at=entries[0].current_version.published_at,
        metadata={"avid": "PUB-001"},
    )
    UserLibraryEntry.objects.filter(user=users[0]).update(current_version=version)
    assert not list_continuations(
        users[0].pk, limit=6, locator=Mock(identities=lambda avids: {})
    )


def test_source_segment_asgi_uses_fixed_metadata_pin_and_cleans_up(
    source_versions, monkeypatch, playback_redis
):
    users, _, entries, clients = source_versions
    row = submit(source_versions)
    records.ready(records.claim(row.pk), descriptor(row))
    row.refresh_from_db()
    gateway, transport, _, registry = make_gateway(
        Response(b"abcd", 206, {"content-range": "bytes 2-5/10", "content-length": "4"})
    )
    gateway.capacity = RedisPlaybackCapacity(playback_redis)
    registry.get = Mock(
        return_value={
            "url": "https://media.example/s.ts",
            "kind": "segment",
            "depth": 1,
        }
    )
    registry.client = Mock()
    monkeypatch.setattr(composition, "build_playback_gateway", lambda: gateway)
    url = f"/nassav/api/playback-sessions/{row.pk}/assets/opaque?cap={capability(row.pk, row.generation, 'opaque')}"

    async def run():
        communicator = HttpCommunicator(
            application,
            "GET",
            url,
            headers=[
                (b"host", b"localhost"),
                (b"cookie", f"sessionid={clients[0].session.session_key}".encode()),
                (b"range", b"bytes=2-5"),
            ],
        )
        await communicator.send_input({"type": "http.request", "body": b""})
        response = await communicator.receive_output(5)
        assert response["status"] == 206
        body = b""
        while True:
            event = await communicator.receive_output(5)
            body += event.get("body", b"")
            if not event.get("more_body", False):
                break
        await communicator.wait(5)
        assert body == b"abcd"

    asyncio.run(run())
    assert transport.closed
    assert not ResourceReadLease.objects.filter(state="active").exists()
    assert ResourceReadLease.objects.get().version_id == entries[0].current_version_id
    assert playback_redis.zcard("nassav:playback:capacity:global") == 0


def test_version_source_disconnect_and_revocation_release_pin_and_capacity(
    source_versions, monkeypatch, playback_redis
):
    users, vault, _, clients = source_versions
    row = submit(source_versions)
    records.ready(records.claim(row.pk), descriptor(row))
    row.refresh_from_db()

    class SlowResponse(Response):
        async def aiter_raw(self, chunk_size=16384):
            yield b"G" * 16384
            await asyncio.sleep(100)

    gateway, transport, _, registry = make_gateway(SlowResponse(b""))
    gateway.capacity = RedisPlaybackCapacity(playback_redis)
    registry.get = Mock(
        return_value={
            "url": "https://media.example/a.ts",
            "kind": "segment",
            "depth": 1,
        }
    )
    registry.client = Mock()
    monkeypatch.setattr(composition, "build_playback_gateway", lambda: gateway)

    async def run():
        communicator = HttpCommunicator(
            application,
            "GET",
            f"/nassav/api/playback-sessions/{row.pk}/assets/opaque?cap={capability(row.pk, row.generation, 'opaque')}",
            headers=[
                (b"host", b"localhost"),
                (b"cookie", f"sessionid={clients[0].session.session_key}".encode()),
            ],
        )
        await communicator.send_input({"type": "http.request", "body": b""})
        assert (await communicator.receive_output(5))["status"] == 200
        assert (await communicator.receive_output(5))["body"]
        await sync_to_async(vault.write)(
            users[0].pk, "jable", {"expected_version": 1}, revoke=True
        )
        from nassav.playback.policy import PlaybackGatewayError

        with pytest.raises(PlaybackGatewayError):
            await communicator.wait(5)

    asyncio.run(run())
    assert transport.closed
    assert not ResourceReadLease.objects.filter(state="active").exists()
    assert ResourceReadLease.objects.get().state == "released"
    assert playback_redis.zcard("nassav:playback:capacity:global") == 0


def test_http_source_submit_uses_own_version_and_wrong_scope_is_not_queued(
    source_versions, monkeypatch
):
    users, _, entries, clients = source_versions
    from nassav.tasks import playback_prepare_task

    dispatch = Mock()
    monkeypatch.setattr(playback_prepare_task, "apply_async", dispatch)
    body = {"request_id": str(uuid4()), "mode": "source"}
    response = clients[0].post(
        "/nassav/api/resources/PUB-001/playback-sessions",
        body,
        content_type="application/json",
    )
    assert response.status_code == 202
    row = records.PlaybackSession.objects.get(pk=response.json()["data"]["session_id"])
    assert row.source == "jable" and row.library_grant["version_id"] == str(
        entries[0].current_version.pk
    )
    assert dispatch.call_args.kwargs["args"] == (str(row.pk),)
    assert (
        clients[0]
        .post(
            "/nassav/api/resources/PUB-001/playback-sessions",
            body,
            content_type="application/json",
        )
        .json()["data"]
        == response.json()["data"]
    )
    assert "credential_id" not in str(response.json()) and "manifest_url" not in str(
        response.json()
    )


def test_source_prepare_rejects_role_epoch_and_downlist_before_network(source_versions):
    from nassav.account_models import UserAccount

    users, _, entries, _ = source_versions
    row = submit(source_versions)
    token = records.claim(row.pk)
    UserAccount.objects.filter(user=users[0]).update(version=2)
    with pytest.raises(records.PlaybackStopped):
        records.check(token)
    other = submit(source_versions, 1)
    token = records.claim(other.pk)
    entries[1].pool.is_available = False
    entries[1].pool.save()
    with pytest.raises(records.PlaybackStopped):
        records.check(token)
