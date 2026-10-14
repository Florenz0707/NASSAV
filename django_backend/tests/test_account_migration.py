"""Account expansion/grants retain previous shared and personal data on both engines."""

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_account_migrations_do_not_guess_roles_or_ownership_and_are_reversible():
    previous = [("nassav", "0037_resource_pool_membership")]
    target = [("nassav", "0039_library_access_grants")]
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    try:
        executor.migrate(previous)
        apps = executor.loader.project_state(previous).apps
        user = apps.get_model("auth", "User").objects.create(
            username="account-migration", is_staff=True, is_superuser=True
        )
        resource = apps.get_model("nassav", "AVResource").objects.create(
            avid="ACC-038", original_title="保留标题", file_size=38
        )
        pool = apps.get_model("nassav", "ResourcePoolEntry").objects.create(
            canonical_avid=resource.avid,
            resource_id=resource.pk,
            state="ready",
            version=7,
        )
        entry = apps.get_model("nassav", "UserLibraryEntry").objects.create(
            user_id=user.pk,
            pool_id=pool.pk,
            state="active",
            access_scope="public",
            version=4,
        )
        apps.get_model("nassav", "UserPreferences").objects.create(
            user_id=user.pk, preferences={"theme": "dark"}
        )
        for _ in range(2):
            executor = MigrationExecutor(connection)
            executor.migrate(target)
            apps = executor.loader.project_state(target).apps
            assert not apps.get_model("nassav", "UserAccount").objects.exists()
            assert (
                apps.get_model("nassav", "ResourcePoolEntry")
                .objects.get(pk=pool.pk)
                .is_available
            )
            assert (
                apps.get_model("nassav", "UserLibraryEntry")
                .objects.get(pk=entry.pk)
                .version
                == 4
            )
            apps.get_model("nassav", "UserAccount").objects.create(
                user_id=user.pk, role="user"
            )
            executor = MigrationExecutor(connection)
            executor.migrate(previous)
            apps = executor.loader.project_state(previous).apps
            assert (
                apps.get_model("nassav", "ResourcePoolEntry")
                .objects.get(pk=pool.pk)
                .version
                == 7
            )
            assert apps.get_model("nassav", "UserPreferences").objects.get(
                user_id=user.pk
            ).preferences == {"theme": "dark"}
            assert (
                apps.get_model("nassav", "AVResource")
                .objects.get(pk=resource.pk)
                .original_title
                == "保留标题"
            )
    finally:
        MigrationExecutor(connection).migrate(latest)
