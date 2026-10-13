import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_viewing_migration_roundtrip_preserves_existing_personal_data():
    previous = [("nassav", "0035_recommendation_user_ownership")]
    target = [("nassav", "0036_viewing_queues")]
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    try:
        executor.migrate(previous)
        apps = executor.loader.project_state(previous).apps
        user = apps.get_model("auth", "User").objects.create(username="view-migration")
        resource = apps.get_model("nassav", "AVResource").objects.create(
            avid="VIEW-036"
        )
        state = apps.get_model("nassav", "UserResourceState").objects.create(
            user_id=user.pk,
            resource_id=resource.pk,
            watched=True,
            is_favorite=True,
            notes="保留",
            version=4,
        )
        for _ in range(2):
            executor = MigrationExecutor(connection)
            executor.migrate(target)
            apps = executor.loader.project_state(target).apps
            row = apps.get_model("nassav", "UserResourceState").objects.get(pk=state.pk)
            assert (row.watched, row.is_favorite, row.notes, row.version) == (
                True,
                True,
                "保留",
                4,
            )
            assert row.watch_later is False and row.watch_later_added_at is None
            assert not apps.get_model("nassav", "UserWatchHistory").objects.exists()
            executor = MigrationExecutor(connection)
            executor.migrate(previous)
            apps = executor.loader.project_state(previous).apps
            assert (
                apps.get_model("nassav", "UserResourceState")
                .objects.get(pk=state.pk)
                .notes
                == "保留"
            )
    finally:
        MigrationExecutor(connection).migrate(latest)
