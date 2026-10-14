"""Version pins authorize owned artifacts, survive pointer changes and bound draining."""

from datetime import timedelta
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.db import transaction, IntegrityError
from django.test import Client
from django.utils import timezone

from nassav.account_models import UserAccount
from nassav.composition import build_library_membership
from nassav.library_models import ResourcePoolEntry, UserLibraryEntry
from nassav.models import AVResource
from nassav.playback import records as playback
from nassav.playback.models import PlaybackSession
from nassav.resource_reads import VersionReads, ReadLeaseNotFound, ReadLeaseConflict
from nassav.resource_read_records import DjangoReadLeases
from nassav.resource_version_models import (
    ResourceVersion,
    ResourceVersionPointer,
    ResourceReadLease,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def context():
    users = [
        get_user_model().objects.create_user(username=name)
        for name in ("read-a", "read-b")
    ]
    clients = []
    for user in users:
        UserAccount.objects.create(user=user)
        client = Client()
        client.force_login(user)
        clients.append(client)
    resource = AVResource.objects.create(avid="READ-001")
    pool = ResourcePoolEntry.objects.create(
        canonical_avid=resource.avid, resource=resource, state="ready"
    )
    version = ResourceVersion.objects.create(
        pool=pool,
        pool_generation=1,
        kind="video",
        source_name="jable",
        access_scope="public",
        context_revision="fixture-v1",
        state="ready",
        published_at=timezone.now(),
        file_size=100,
        media_identity="a" * 64,
        manifest=[{"root": "video", "path": "fixture-only"}],
    )
    entries = [
        UserLibraryEntry.objects.create(
            user=user,
            pool=pool,
            state="active",
            desired_spec={"source": "jable"},
            access_scope="public",
            video_version=version,
        )
        for user in users
    ]
    pointers = ResourceVersionPointer.objects.create(
        pool=pool,
        source_name="jable",
        access_scope="public",
        kind="video",
        current=version,
    )
    return (
        users,
        [client.session.session_key for client in clients],
        pool,
        version,
        entries,
        pointers,
        VersionReads(DjangoReadLeases()),
    )


def test_pin_is_owned_idempotent_and_never_contains_paths_or_credentials(context):
    users, keys, _, version, _, _, reads = context
    command = uuid4()
    pin = reads.pin(users[0].pk, keys[0], version.pk, command)
    assert reads.pin(users[0].pk, keys[0], version.pk, command) == pin
    assert ResourceReadLease.objects.count() == 1
    assert (
        "manifest" not in pin
        and "login_hash" not in pin
        and "credential_refs" not in pin
    )
    with pytest.raises(ReadLeaseNotFound):
        reads.check(users[1].pk, keys[1], pin["lease_id"])
    with pytest.raises(ReadLeaseNotFound):
        reads.check(users[0].pk, keys[1], pin["lease_id"])


def test_private_version_cannot_be_pinned_by_another_holder_or_admin(context):
    users, keys, _, version, entries, _, reads = context
    version.access_scope = f"personal:{uuid4()}"
    version.owner = users[0]
    version.save()
    for entry in entries:
        entry.access_scope = version.access_scope
        entry.save()
    UserAccount.objects.filter(user=users[1]).update(role="admin")
    reads.pin(users[0].pk, keys[0], version.pk, uuid4())
    with pytest.raises(ReadLeaseNotFound):
        reads.pin(users[1].pk, keys[1], version.pk, uuid4())


def test_renew_cas_and_release_cannot_revive_old_pin(context):
    users, keys, _, version, _, _, reads = context
    command = uuid4()
    first = reads.pin(users[0].pk, keys[0], version.pk, command)
    renewed = reads.renew(users[0].pk, keys[0], first["lease_id"], expected_revision=1)
    assert renewed["revision"] == 2
    assert renewed["absolute_expires_at"] == first["absolute_expires_at"]
    with pytest.raises(ReadLeaseConflict, match="revision_conflict"):
        reads.renew(users[0].pk, keys[0], first["lease_id"], expected_revision=1)
    released = reads.release(users[0].pk, keys[0], first["lease_id"])
    assert reads.release(users[0].pk, keys[0], first["lease_id"]) == released
    with pytest.raises(ReadLeaseConflict, match="expired"):
        reads.renew(
            users[0].pk,
            keys[0],
            first["lease_id"],
            expected_revision=released["revision"],
        )
    with pytest.raises(ReadLeaseConflict, match="expired"):
        reads.pin(users[0].pk, keys[0], version.pk, command)
    assert not DjangoReadLeases.has_readers(version.pk)


def test_expired_pin_does_not_block_and_cannot_be_renewed(context):
    users, keys, _, version, _, _, reads = context
    pin = reads.pin(users[0].pk, keys[0], version.pk, uuid4())
    ResourceReadLease.objects.filter(pk=pin["lease_id"]).update(
        expires_at=timezone.now() - timedelta(seconds=1)
    )
    assert not DjangoReadLeases.has_readers(version.pk)
    with pytest.raises(ReadLeaseConflict, match="expired"):
        reads.renew(users[0].pk, keys[0], pin["lease_id"], expected_revision=1)


def test_playback_pin_fixed_version_drains_after_release_but_downlist_revokes(context):
    users, keys, pool, version, entries, pointer, reads = context
    session = playback.submit(
        users[0].pk,
        keys[0],
        pool.resource.avid,
        uuid4(),
        mode="local",
        descriptor={"fixture": "not-media-acceptance"},
    )
    session.library_grant = {**session.library_grant, "version_id": str(version.pk)}
    session.save()
    pin = reads.pin(
        users[0].pk, keys[0], version.pk, uuid4(), playback_session_id=session.pk
    )
    newer = ResourceVersion.objects.create(
        pool=pool,
        pool_generation=1,
        kind="video",
        source_name="jable",
        access_scope="public",
        context_revision="new-fixture",
        state="ready",
        published_at=timezone.now(),
    )
    pointer.current = newer
    pointer.revision += 1
    pointer.save()
    assert reads.check(users[0].pk, keys[0], pin["lease_id"])["version_id"] == str(
        version.pk
    )
    for entry, user in zip(entries, users):
        build_library_membership().release(user.pk, entry.pk, expected_version=1)
    assert ResourcePoolEntry.objects.get().state == "pending_gc"
    assert reads.check(users[0].pk, keys[0], pin["lease_id"])["version_id"] == str(
        version.pk
    )
    second_pin = reads.pin(
        users[0].pk, keys[0], version.pk, uuid4(), playback_session_id=session.pk
    )
    assert second_pin["absolute_expires_at"] == session.absolute_expires_at.isoformat()
    from nassav.playback.contracts import PlaybackStopped

    with pytest.raises(PlaybackStopped):
        playback.submit(
            users[0].pk,
            keys[0],
            pool.resource.avid,
            uuid4(),
            mode="local",
            descriptor={"fixture": True},
        )
    ResourcePoolEntry.objects.filter(pk=pool.pk).update(is_available=False)
    with pytest.raises(ReadLeaseNotFound):
        reads.check(users[0].pk, keys[0], pin["lease_id"])


def test_closed_session_and_logout_or_epoch_change_reject_old_reads(context):
    from django.contrib.sessions.models import Session

    users, keys, pool, version, _, _, reads = context
    session = playback.submit(
        users[0].pk,
        keys[0],
        pool.resource.avid,
        uuid4(),
        mode="local",
        descriptor={"fixture": True},
    )
    session.library_grant = {**session.library_grant, "version_id": str(version.pk)}
    session.save()
    pin = reads.pin(
        users[0].pk, keys[0], version.pk, uuid4(), playback_session_id=session.pk
    )
    PlaybackSession.objects.filter(pk=session.pk).update(state="closed")
    with pytest.raises(ReadLeaseNotFound):
        reads.check(users[0].pk, keys[0], pin["lease_id"])
    other = reads.pin(users[1].pk, keys[1], version.pk, uuid4())
    UserAccount.objects.filter(user=users[1]).update(version=2)
    with pytest.raises(ReadLeaseNotFound):
        reads.check(users[1].pk, keys[1], other["lease_id"])
    Session.objects.filter(session_key=keys[1]).delete()
    with pytest.raises(ReadLeaseNotFound):
        reads.check(users[1].pk, keys[1], other["lease_id"])


def test_schema_rejects_ownerless_private_publication_and_invalid_deadline(context):
    users, _, pool, version, _, _, _ = context
    with pytest.raises(IntegrityError), transaction.atomic():
        ResourceVersion.objects.create(
            pool=pool,
            pool_generation=1,
            kind="metadata",
            source_name="jable",
            access_scope="personal:missing-owner",
            context_revision="fixture",
        )
    with pytest.raises(IntegrityError), transaction.atomic():
        ResourceReadLease.objects.create(
            user_id=users[0].pk,
            version=version,
            request_id=uuid4(),
            login_hash="fixture",
            expires_at=timezone.now() + timedelta(minutes=3),
            absolute_expires_at=timezone.now(),
        )


@pytest.mark.django_db(transaction=True)
def test_concurrent_renew_and_release_leave_no_active_pin(context):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from django.db import close_old_connections

    users, keys, _, version, _, _, reads = context
    pin = reads.pin(users[0].pk, keys[0], version.pk, uuid4())
    barrier = Barrier(2)

    def run(action):
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            try:
                return action()
            except ReadLeaseConflict as error:
                return str(error)
        finally:
            close_old_connections()

    actions = [
        lambda: reads.renew(users[0].pk, keys[0], pin["lease_id"], expected_revision=1),
        lambda: reads.release(users[0].pk, keys[0], pin["lease_id"]),
    ]
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(run, actions))
    assert isinstance(results[1], dict) and results[1]["state"] == "released"
    assert ResourceReadLease.objects.get().state == "released"
    assert not DjangoReadLeases.has_readers(version.pk)


@pytest.mark.django_db(transaction=True)
def test_concurrent_idempotent_pin_creates_one_row(context):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from django.db import close_old_connections

    users, keys, _, version, _, _, reads = context
    command = uuid4()
    barrier = Barrier(2)

    def run(_):
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            return reads.pin(users[0].pk, keys[0], version.pk, command)
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(run, range(2)))
    assert results[0] == results[1]
    assert ResourceReadLease.objects.count() == 1
