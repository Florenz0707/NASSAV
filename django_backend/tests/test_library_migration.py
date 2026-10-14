"""0037 is additive: no implicit owner assignment or legacy-row mutations."""

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_pool_migration_upgrade_reverse_upgrade_preserves_existing_data():
    previous = [("nassav", "0036_viewing_queues")]
    target = [("nassav", "0037_resource_pool_membership")]
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    try:
        executor.migrate(previous)
        apps = executor.loader.project_state(previous).apps
        user = apps.get_model("auth", "User").objects.create(username="pool-migration")
        resource = apps.get_model("nassav", "AVResource").objects.create(
            avid="POOL-037",
            original_title="保留标题",
            source="jable",
            file_size=1234,
            watched=True,
        )
        actor = apps.get_model("nassav", "Actor").objects.create(name="保留演员")
        resource.actors.add(actor)
        apps.get_model("nassav", "UserResourceState").objects.create(
            user_id=user.pk, resource_id=resource.pk, notes="保留备注", version=7
        )
        for _ in range(2):
            executor = MigrationExecutor(connection)
            executor.migrate(target)
            apps = executor.loader.project_state(target).apps
            loaded = apps.get_model("nassav", "AVResource").objects.get(pk=resource.pk)
            assert (loaded.original_title, loaded.file_size, loaded.watched) == (
                "保留标题",
                1234,
                True,
            )
            assert list(loaded.actors.values_list("pk", flat=True)) == [actor.pk]
            assert (
                apps.get_model("nassav", "UserResourceState")
                .objects.get(user_id=user.pk)
                .notes
                == "保留备注"
            )
            assert not apps.get_model("nassav", "ResourcePoolEntry").objects.exists()
            assert not apps.get_model("nassav", "UserLibraryEntry").objects.exists()
            pool = apps.get_model("nassav", "ResourcePoolEntry").objects.create(
                canonical_avid=loaded.avid, resource_id=loaded.pk, state="ready"
            )
            apps.get_model("nassav", "UserLibraryEntry").objects.create(
                user_id=user.pk,
                pool_id=pool.pk,
                state="active",
                access_scope="legacy:operator",
            )
            executor = MigrationExecutor(connection)
            executor.migrate(previous)
            apps = executor.loader.project_state(previous).apps
            assert (
                apps.get_model("nassav", "AVResource")
                .objects.get(pk=resource.pk)
                .file_size
                == 1234
            )
            assert (
                apps.get_model("nassav", "UserResourceState")
                .objects.get(user_id=user.pk)
                .version
                == 7
            )
    finally:
        MigrationExecutor(connection).migrate(latest)
