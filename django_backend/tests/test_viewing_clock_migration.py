"""Existing events roundtrip; deleted-event logical-time fences must not be lost."""

from datetime import timedelta
import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone


@pytest.mark.django_db(transaction=True)
def test_viewing_clock_roundtrip_and_deleted_event_fence_guard():
    old = [("nassav", "0048_durable_viewing_history")]
    new = [("nassav", "0049_viewing_history_clock")]
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    try:
        executor.migrate(old)
        apps = executor.loader.project_state(old).apps
        user = apps.get_model("auth", "User").objects.create(username="clock-049")
        pool = apps.get_model("nassav", "ResourcePoolEntry").objects.create(
            canonical_avid="CLOCK-049"
        )
        stamp = timezone.now()
        history = apps.get_model("nassav", "UserWatchHistory").objects.create(
            user_id=user.pk,
            pool_id=pool.pk,
            resource=None,
            snapshot={"avid": "CLOCK-049"},
            last_watched_at=stamp,
            media_kind="local",
        )
        for _ in range(2):
            executor = MigrationExecutor(connection)
            executor.migrate(new)
            apps = executor.loader.project_state(new).apps
            assert (
                apps.get_model("nassav", "UserViewingClock")
                .objects.get(user_id=user.pk)
                .last_recorded_at
                == stamp
            )
            assert (
                apps.get_model("nassav", "UserWatchHistory")
                .objects.get(pk=history.pk)
                .last_watched_at
                == stamp
            )
            executor = MigrationExecutor(connection)
            executor.migrate(old)
        executor = MigrationExecutor(connection)
        executor.migrate(new)
        apps = executor.loader.project_state(new).apps
        apps.get_model("nassav", "UserViewingClock").objects.filter(
            user_id=user.pk
        ).update(last_recorded_at=stamp + timedelta(microseconds=1))
        with pytest.raises(RuntimeError, match="restore backup"):
            MigrationExecutor(connection).migrate(old)
        assert (
            MigrationExecutor(connection)
            .loader.project_state(new)
            .apps.get_model("nassav", "UserViewingClock")
            .objects.get(user_id=user.pk)
            .last_recorded_at
            > stamp
        )
    finally:
        MigrationExecutor(connection).migrate(latest)
