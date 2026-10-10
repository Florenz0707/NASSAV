from dataclasses import asdict
from datetime import timedelta
from uuid import uuid4
from unittest.mock import Mock
import pytest
from django.utils import timezone
from rest_framework.test import APIClient
from nassav.playback import records
from nassav.playback.contracts import PlaybackDescriptor, PlaybackStopped
from nassav.playback.preparation import execute
from nassav.models import PlaybackSession, ResourcePlaybackCache

pytestmark = pytest.mark.django_db


def session(operator_user, resource_factory):
    resource = resource_factory(source="Jable")
    return records.submit(operator_user.pk, "login-one", resource.avid, uuid4())


def descriptor():
    return PlaybackDescriptor(
        "https://media.example/v.m3u8",
        "https://source.example/detail",
        "test-UA",
        "jable",
        None,
        None,
    )


def test_close_fences_old_execution_cache_and_publication(
    operator_user, resource_factory
):
    row = session(operator_user, resource_factory)
    token = records.claim(row.pk)
    assert records.claim(row.pk) is None
    row.refresh_from_db()
    command = uuid4()
    closed = records.close(row.pk, operator_user.pk, "login-one", row.version, command)
    assert (
        records.close(
            row.pk, operator_user.pk, "login-one", row.version, command
        ).version
        == closed.version
    )
    with pytest.raises(PlaybackStopped):
        records.ready(token, descriptor())
    operation = Mock()
    with pytest.raises(PlaybackStopped):
        records.publish(token, operation)
    operation.assert_not_called()
    assert not ResourcePlaybackCache.objects.exists()


def test_prepare_success_snapshot_is_private_and_delete_fences(
    operator_user, resource_factory
):
    row = session(operator_user, resource_factory)
    resolver = Mock()
    resolver.resolve.return_value = descriptor()
    execute(row.pk, resolver, records)
    row.refresh_from_db()
    assert row.state == "ready" and row.descriptor == asdict(descriptor())
    assert "manifest_url" not in records.snapshot(row)
    assert "login_hash" not in records.snapshot(row)
    row.resource.delete()
    assert not PlaybackSession.objects.exists()


def test_dispatch_retry_expiry_and_lease_loss(operator_user, resource_factory):
    row = session(operator_user, resource_factory)
    broken = Mock(side_effect=RuntimeError())
    records.recover(broken)
    broken.assert_called_once()
    records.recover(broken)
    assert broken.call_count == 1
    token = records.claim(row.pk)
    PlaybackSession.objects.filter(pk=row.pk).update(
        lease_until=timezone.now() - timedelta(seconds=1)
    )
    with pytest.raises(PlaybackStopped):
        records.check(token)
    records.recover(Mock())
    row.refresh_from_db()
    assert row.state == "failed"


def test_create_idempotent_and_capacity_per_user(operator_user, resource_factory):
    row = session(operator_user, resource_factory)
    assert (
        records.submit(
            operator_user.pk, "login-one", row.resource.avid, row.request_id
        ).pk
        == row.pk
    )
    records.submit(operator_user.pk, "login-two", row.resource.avid, uuid4())
    with pytest.raises(PlaybackStopped):
        records.submit(operator_user.pk, "login-three", row.resource.avid, uuid4())
    with pytest.raises(PlaybackSession.DoesNotExist):
        records.owned(row.pk, operator_user.pk, "login-two")


def test_failure_and_cancelled_resolver_do_not_publish(operator_user, resource_factory):
    row = session(operator_user, resource_factory)
    resolver = Mock()
    resolver.resolve.side_effect = ValueError("private URL")
    execute(row.pk, resolver, records)
    row.refresh_from_db()
    assert row.error_code == "preparation_failed"
    assert "private" not in str(records.snapshot(row))


def test_api_operator_disabled_login_binding_and_csrf(
    operator_user, resource_factory, settings, monkeypatch
):
    settings.PLAYBACK_ENABLED = True
    resource = resource_factory(source="Jable")
    from nassav.tasks import playback_prepare_task

    monkeypatch.setattr(playback_prepare_task, "apply_async", Mock())
    url = f"/nassav/api/resources/{resource.avid}/playback-sessions"
    client = APIClient()
    assert client.post(url, {}, format="json").status_code == 401
    client.force_login(operator_user)
    response = client.post(url, {"request_id": str(uuid4())}, format="json")
    assert response.status_code == 202
    sid = response.json()["data"]["session_id"]
    assert client.get(f"/nassav/api/playback-sessions/{sid}").status_code == 200
    other = APIClient()
    other.force_login(operator_user)
    assert other.get(f"/nassav/api/playback-sessions/{sid}").status_code == 404
    csrf = APIClient(enforce_csrf_checks=True)
    csrf.force_login(operator_user)
    assert (
        csrf.post(url, {"request_id": str(uuid4())}, format="json").status_code == 403
    )
    settings.PLAYBACK_ENABLED = False
    assert client.get(f"/nassav/api/playback-sessions/{sid}").status_code == 404


def test_logout_closes_all_bound_sessions_and_blocks_old_publish(
    operator_user, resource_factory
):
    row = session(operator_user, resource_factory)
    token = records.claim(row.pk)
    records.close_login("login-one")
    row.refresh_from_db()
    assert row.state == "closed"
    with pytest.raises(PlaybackStopped):
        records.ready(token, descriptor())


def test_online_cache_is_versioned_contextual_and_owned(
    operator_user, resource_factory
):
    from contextlib import contextmanager
    from nassav.composition import build_provider_facts_cache
    from nassav.playback.preparation import SourcePlaybackResolver
    from nassav.task_network import TaskNetworkControl

    row = session(operator_user, resource_factory)
    token = records.claim(row.pk)
    source = Mock()
    source.proxy = None
    source.domain = "source.example"
    source.browser_session_version.return_value = "session-v1"
    source.last_final_url = "https://source.example/detail"
    source.get_html.return_value = "valid-page"
    source.parse_html.return_value = Mock(
        avid=row.resource.avid, m3u8="https://media.example/v.m3u8"
    )

    @contextmanager
    def scope(name, control):
        yield source

    resolver = SourcePlaybackResolver(scope, build_provider_facts_cache(), 300)
    control = TaskNetworkControl(
        lambda: records.check(token),
        publish_fence=lambda op: records.publish(token, op),
    )
    assert (
        resolver.resolve(row.resource.avid, row.source, control).schema
        == "online-playback-v2"
    )
    resolver.resolve(row.resource.avid, row.source, control)
    assert source.get_html.call_count == 1
    source.browser_session_version.return_value = "session-v2"
    resolver.resolve(row.resource.avid, row.source, control)
    assert source.get_html.call_count == 2
    row.refresh_from_db()
    records.close(row.pk, operator_user.pk, "login-one", row.version, uuid4())
    with pytest.raises(PlaybackStopped):
        resolver.resolve(row.resource.avid, row.source, control)
