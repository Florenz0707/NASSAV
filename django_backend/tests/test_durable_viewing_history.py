"""Snapshots are personal display history, never grants to released resources."""

from uuid import uuid4

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from nassav.library_models import UserLibraryEntry
from nassav.account_models import UserAccount
from nassav.resource_version_models import ResourceVersion
from nassav.personal_models import UserWatchHistory
from nassav.personal_state import update_state
from nassav.playback import records
from nassav.playback.policy import PlaybackGatewayError
from nassav.viewing import record_view, list_viewing, remove_history
from test_version_source_playback import source_versions as source_versions, submit
from test_version_publication import environment as environment
from test_version_local_playback import clip as clip

pytestmark = pytest.mark.django_db


def ready(row):
    row.state = "ready"
    row.save(update_fields=["state"])
    return row


def test_fixed_version_titles_owned_lists_and_released_history(source_versions):
    users, _, entries, clients = source_versions
    rows = [ready(submit(source_versions, index)) for index in (0, 1)]
    for index, row in enumerate(rows):
        record_view(row.pk, users[index].pk, clients[index].session.session_key, 1, 1)
        update_state(
            entries[index].pool.resource, users[index].pk, {"watch_later": True}
        )
    for index, user in enumerate(users):
        data, pagination = list_viewing(user.pk, "history", 1, 15)
        assert pagination["total"] == 1
        assert data[0]["source_title"] == f"private title {user.pk}"
        assert data[0]["is_available"] is True
        later = list_viewing(user.pk, "watch-later", 1, 15)[0]
        assert later[0]["source_title"] == data[0]["source_title"]
    # Pointer changes cannot rewrite the display facts of this playback event.
    previous = entries[0].current_version
    updated = ResourceVersion.objects.create(
        pool=previous.pool,
        pool_generation=previous.pool_generation,
        owner=previous.owner,
        kind=previous.kind,
        source_name=previous.source_name,
        access_scope=previous.access_scope,
        context_revision=previous.context_revision,
        credential_refs=previous.credential_refs,
        state="ready",
        published_at=timezone.now(),
        metadata={**previous.metadata, "source_title": "new version title"},
    )
    UserLibraryEntry.objects.filter(pk=entries[0].pk).update(current_version=updated)
    assert (
        list_viewing(users[0].pk, "history", 1, 15)[0][0]["source_title"]
        == f"private title {users[0].pk}"
    )
    # Simulate completed release without deleting the shared anchor belonging to B.
    UserLibraryEntry.objects.filter(pk=entries[0].pk).delete()
    assert list_viewing(users[0].pk, "watch-later", 1, 15)[1]["total"] == 0
    item = list_viewing(users[0].pk, "history", 1, 15)[0][0]
    assert item["is_available"] is False and item["thumbnail_url"] is None
    assert item["source_title"] != f"private title {users[1].pk}"
    assert not any(
        key in item for key in ("credential_refs", "m3u8", "descriptor", "manifest")
    )
    # Original fixed session can still drain, but an account-epoch change cannot.
    record_view(rows[0].pk, users[0].pk, clients[0].session.session_key, 1, 2)
    account = UserAccount.objects.get(user=users[0])
    account.version += 1
    account.save(update_fields=["version"])
    with pytest.raises(PlaybackGatewayError):
        record_view(rows[0].pk, users[0].pk, clients[0].session.session_key, 1, 3)


def test_anchor_deleted_history_retains_identity_and_cas_delete(source_versions):
    users, _, entries, clients = source_versions
    row = ready(submit(source_versions))
    record_view(row.pk, users[0].pk, clients[0].session.session_key, 1, 1)
    item = list_viewing(users[0].pk, "history", 1, 15)[0][0]
    records.close(
        row.pk, users[0].pk, clients[0].session.session_key, row.version, uuid4()
    )
    entries[0].pool.resource.delete()
    history = UserWatchHistory.objects.get(user=users[0])
    assert history.resource_id is None
    data = list_viewing(users[0].pk, "history", 1, 15)[0][0]
    assert data["avid"] == "PUB-001" and data["source_title"] == item["source_title"]
    assert data["is_available"] is False and data["thumbnail_url"] is None
    assert (
        remove_history(
            users[1].pk, [{"avid": data["avid"], "queue_time": data["queue_time"]}]
        )[0]["status"]
        == "absent"
    )
    assert (
        remove_history(
            users[0].pk, [{"avid": data["avid"], "queue_time": data["queue_time"]}]
        )[0]["status"]
        == "removed"
    )


@pytest.mark.django_db(transaction=True)
def test_history_migration_roundtrip_keeps_events_and_refuses_loss_after_reclamation():
    old = [("nassav", "0047_owned_catalog_projection")]
    new = [("nassav", "0048_durable_viewing_history")]
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    try:
        executor.migrate(old)
        apps = executor.loader.project_state(old).apps
        user = apps.get_model("auth", "User").objects.create(username="history-048")
        resource = apps.get_model("nassav", "AVResource").objects.create(
            avid="HIST-048", source="jable", source_title="原来标题"
        )
        stamp = timezone.now()
        history = apps.get_model("nassav", "UserWatchHistory").objects.create(
            user_id=user.pk,
            resource_id=resource.pk,
            media_kind="source",
            last_watched_at=stamp,
        )
        for _ in range(2):
            executor = MigrationExecutor(connection)
            executor.migrate(new)
            apps = executor.loader.project_state(new).apps
            row = apps.get_model("nassav", "UserWatchHistory").objects.get(
                pk=history.pk
            )
            assert row.snapshot["source_title"] == "原来标题"
            assert row.pool.canonical_avid == "HIST-048"
            assert row.last_watched_at == stamp and row.user_id == user.pk
            assert not apps.get_model("nassav", "UserLibraryEntry").objects.exists()
            executor = MigrationExecutor(connection)
            executor.migrate(old)
            row = (
                executor.loader.project_state(old)
                .apps.get_model("nassav", "UserWatchHistory")
                .objects.get(pk=history.pk)
            )
            assert row.resource_id == resource.pk and row.last_watched_at == stamp
        executor = MigrationExecutor(connection)
        executor.migrate(new)
        apps = executor.loader.project_state(new).apps
        apps.get_model("nassav", "AVResource").objects.get(pk=resource.pk).delete()
        with pytest.raises(RuntimeError, match="restore backup"):
            MigrationExecutor(connection).migrate(old)
        apps = MigrationExecutor(connection).loader.project_state(new).apps
        assert (
            apps.get_model("nassav", "UserWatchHistory")
            .objects.get(pk=history.pk)
            .resource_id
            is None
        )
    finally:
        MigrationExecutor(connection).migrate(latest)


@pytest.mark.django_db(transaction=True)
def test_local_history_uses_video_snapshot_and_remains_independent_of_progress(clip):
    from test_version_local_playback import session
    from nassav.playback.models import PlaybackProgress

    users, client, version, _ = clip
    row = session(clip)
    record_view(row.pk, users[0].pk, client.session.session_key, 1, 1)
    item = list_viewing(users[0].pk, "history", 1, 15)[0][0]
    assert item["source_title"] == version.metadata["source_title"]
    assert item["is_available"] is True
    assert not PlaybackProgress.objects.exists()


def test_reclaimed_history_projection_is_bounded_not_per_item(source_versions):
    from django.test.utils import CaptureQueriesContext
    from nassav.library_models import ResourcePoolEntry

    users, _, _, _ = source_versions
    for index in range(20):
        pool = ResourcePoolEntry.objects.create(
            canonical_avid=f"RECLAIMED-{index}", state="reclaimed"
        )
        UserWatchHistory.objects.create(
            user=users[0],
            pool=pool,
            resource=None,
            snapshot={"avid": pool.canonical_avid, "source_title": "旧标题"},
            media_kind="source",
            last_watched_at=timezone.now(),
        )
    with CaptureQueriesContext(connection) as queries:
        data, pagination = list_viewing(users[0].pk, "history", 1, 20)
    assert pagination["total"] == 20 and len(data) == 20
    assert all(
        not item["is_available"] and item["thumbnail_url"] is None for item in data
    )
    assert len(queries) <= 4
