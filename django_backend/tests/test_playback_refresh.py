"""One-shot refresh, timeline compatibility and old execution fencing."""

import asyncio
from datetime import timedelta
from uuid import uuid4
from unittest.mock import Mock
import pytest
from django.utils import timezone
from nassav.playback import records
from nassav.playback.contracts import PlaybackStopped
from nassav.playback.identity import (
    PlaybackIdentityValidator,
    manifest_digest,
    byte_digest,
)
from nassav.playback.preparation import execute
from nassav.playback.policy import PlaybackGatewayError
from nassav.playback.manifest import parse_manifest
from nassav.playback.models import PlaybackSession
from test_playback_sessions import descriptor
from test_playback_gateway import policy, Response, Capacity
from contextlib import asynccontextmanager


def playlist(suffix="old", duration="4"):
    return f'#EXTM3U\n#EXT-X-TARGETDURATION:4\n#EXT-X-KEY:METHOD=AES-128,URI="key?sig={suffix}",IV=0x01\n#EXT-X-MAP:URI="init.mp4?sig={suffix}"\n#EXTINF:{duration},\nsegment.ts?sig={suffix}\n#EXT-X-ENDLIST\n'.encode()


class Transport:
    def __init__(self, body, key=b"k" * 16, init=b"\x00\x00\x00\x18ftypisom"):
        self.body, self.key, self.init, self.responses = body, key, init, []

    @asynccontextmanager
    async def open(self, url, headers):
        body = (
            self.key
            if "/key?" in url
            else self.init
            if "/init.mp4?" in url
            else self.body
        )
        response = Response(body)
        self.responses.append(response)
        try:
            yield response, url
        finally:
            await response.aclose()


def baseline():
    parsed = parse_manifest(playlist(), "https://media.example/v.m3u8", policy())
    return {
        "root": {"kind": "manifest", "digest": manifest_digest(parsed)},
        "root/0": {"kind": "key", "digest": byte_digest(b"k" * 16)},
        "root/1": {"kind": "init", "digest": byte_digest(b"\x00\x00\x00\x18ftypisom")},
    }


def test_refresh_accepts_signed_url_changes_and_checks_key_init_and_time_axis():
    for transport, success in [
        (Transport(playlist("new")), True),
        (Transport(playlist("new", "5")), False),
        (Transport(playlist("new"), key=b"x" * 16), False),
        (Transport(playlist("new"), init=b"different-init"), False),
    ]:
        capacity = Capacity()
        validator = PlaybackIdentityValidator(transport, policy(), capacity)
        if success:
            asyncio.run(
                validator.verify(uuid4(), descriptor(), baseline(), lambda: None)
            )
        else:
            with pytest.raises(PlaybackGatewayError, match="media_identity_changed"):
                asyncio.run(
                    validator.verify(uuid4(), descriptor(), baseline(), lambda: None)
                )
        assert capacity.active == 0
        assert all(response.closed for response in transport.responses)


@pytest.mark.django_db
def test_refresh_new_generation_is_single_flight_bounded_and_close_fences(
    operator_user, resource_factory
):
    resource = resource_factory(source="Jable")
    row = records.submit(operator_user.pk, "login", resource.avid, uuid4())
    first = records.claim(row.pk)
    records.ready(first, descriptor())
    records.observe_identity(
        row.pk, 1, "root", "manifest", baseline()["root"]["digest"]
    )
    row.refresh_from_db()
    original_expiry = row.absolute_expires_at
    command = uuid4()
    refreshed = records.refresh(row.pk, operator_user.pk, "login", row.version, command)
    assert refreshed.generation == 2 and refreshed.refresh_count == 1
    assert refreshed.absolute_expires_at == original_expiry
    assert (
        records.refresh(row.pk, operator_user.pk, "login", row.version, command).pk
        == row.pk
    )
    with pytest.raises(PlaybackStopped):
        records.refresh(row.pk, operator_user.pk, "login", refreshed.version, uuid4())
    with pytest.raises(PlaybackGatewayError):
        records.observe_identity(row.pk, 1, "root", "manifest", "late")
    with pytest.raises(PlaybackStopped):
        records.ready(first, descriptor())
    second = records.claim(row.pk)
    refreshed.refresh_from_db()
    records.close(row.pk, operator_user.pk, "login", refreshed.version, uuid4())
    with pytest.raises(PlaybackStopped):
        records.ready(second, descriptor())
    assert not PlaybackSession.objects.get(pk=row.pk).descriptor


@pytest.mark.django_db
def test_worker_force_refresh_is_validated_before_ready_or_failure(
    operator_user, resource_factory
):
    resource = resource_factory(source="Jable")
    row = records.submit(operator_user.pk, "login", resource.avid, uuid4())
    records.ready(records.claim(row.pk), descriptor())
    records.observe_identity(row.pk, 1, "root", "manifest", "hash")
    row.refresh_from_db()
    records.refresh(row.pk, operator_user.pk, "login", row.version, uuid4())
    resolver, validator = Mock(), Mock()
    resolver.resolve.return_value = descriptor()
    validator.validate.side_effect = PlaybackGatewayError("media_identity_changed", 422)
    execute(row.pk, resolver, records, validator)
    row.refresh_from_db()
    assert row.state == "failed" and row.error_code == "media_identity_changed"
    assert not row.descriptor
    assert resolver.resolve.call_args.kwargs["force"] is True
    validator.validate.assert_called_once()


@pytest.mark.django_db
def test_refresh_requires_complete_observations_and_preserves_ttl(
    operator_user, resource_factory
):
    row = records.submit(
        operator_user.pk, "login", resource_factory(source="Jable").avid, uuid4()
    )
    records.ready(records.claim(row.pk), descriptor())
    records.observe_identity(row.pk, 1, "root", "manifest", "hash", [("root/0", "key")])
    row.refresh_from_db()
    assert "refresh" not in records.snapshot(row)["allowed_actions"]
    with pytest.raises(PlaybackStopped):
        records.refresh(row.pk, operator_user.pk, "login", row.version, uuid4())
    records.observe_identity(row.pk, 1, "root/0", "key", "key-hash")
    row.refresh_from_db()
    assert "refresh" in records.snapshot(row)["allowed_actions"]
    PlaybackSession.objects.filter(pk=row.pk).update(
        idle_expires_at=timezone.now() - timedelta(seconds=1)
    )
    with pytest.raises(PlaybackStopped):
        records.refresh(row.pk, operator_user.pk, "login", row.version, uuid4())


@pytest.mark.django_db
def test_refresh_http_requires_auth_csrf_version_and_uses_real_dispatch_contract(
    operator_user, resource_factory, settings, monkeypatch
):
    from rest_framework.test import APIClient
    from nassav.tasks import playback_prepare_task

    settings.PLAYBACK_ENABLED = True
    dispatched = Mock()
    monkeypatch.setattr(playback_prepare_task, "apply_async", dispatched)
    client = APIClient()
    client.force_login(operator_user)
    resource = resource_factory(source="Jable")
    created = client.post(
        f"/nassav/api/resources/{resource.avid}/playback-sessions",
        {"request_id": str(uuid4())},
        format="json",
    ).json()["data"]
    sid = created["session_id"]
    records.ready(records.claim(sid), descriptor())
    records.observe_identity(sid, 1, "root", "manifest", "hash")
    version = PlaybackSession.objects.get(pk=sid).version
    url = f"/nassav/api/playback-sessions/{sid}/refresh"
    payload = {"request_id": str(uuid4()), "expected_version": version}
    assert APIClient().post(url, payload, format="json").status_code == 401
    csrf = APIClient(enforce_csrf_checks=True)
    csrf.force_login(operator_user)
    assert csrf.post(url, payload, format="json").status_code == 403
    response = client.post(url, payload, format="json")
    assert response.status_code == 202 and response.json()["data"]["generation"] == 2
    assert dispatched.call_args.kwargs == {"args": (sid,), "queue": "scrape"}
    assert (
        client.post(url, payload, format="json").json()["data"]["version"]
        == response.json()["data"]["version"]
    )


def test_manifest_identity_ignores_nonsemantic_comments_and_unknown_tags():
    original = parse_manifest(playlist(), "https://media.example/v.m3u8", policy())
    changed = parse_manifest(
        playlist("new").replace(
            b"#EXTM3U\n",
            b"#EXTM3U\n# vendor comment\n\n#EXT-X-UNKNOWN=rotating-token\n",
        ),
        "https://media.example/v.m3u8",
        policy(),
    )
    assert manifest_digest(original) == manifest_digest(changed)
    # Standard tags affecting media structure must still change the identity.
    for tag in (
        b"#EXT-X-MEDIA-SEQUENCE:1\n",
        b"#EXT-X-DISCONTINUITY\n",
        b"#EXT-X-GAP\n",
    ):
        different = parse_manifest(
            playlist().replace(b"#EXTINF:", tag + b"#EXTINF:"),
            "https://media.example/v.m3u8",
            policy(),
        )
        assert manifest_digest(original) != manifest_digest(different)
