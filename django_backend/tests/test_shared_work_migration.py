"""Additive demand schema retains pool membership and existing task attempts."""

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_shared_work_migration_roundtrip_retains_legacy_tasks_and_memberships():
    previous = [("nassav", "0041_source_credential_key_policy")]
    target = [("nassav", "0042_shared_work_subscriptions")]
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    try:
        executor.migrate(previous)
        apps = executor.loader.project_state(previous).apps
        user = apps.get_model("auth", "User").objects.create(
            username="shared-migration"
        )
        pool = apps.get_model("nassav", "ResourcePoolEntry").objects.create(
            canonical_avid="SHARED-042"
        )
        entry = apps.get_model("nassav", "UserLibraryEntry").objects.create(
            user_id=user.pk,
            pool_id=pool.pk,
            access_scope="public",
            desired_spec={"source": "jable"},
        )
        job = apps.get_model("nassav", "TaskJob").objects.create(
            kind="scrape",
            action="add",
            avid="SHARED-042",
            owner_id=user.pk,
            options={"source": "jable"},
        )
        attempt = apps.get_model("nassav", "TaskAttempt").objects.create(
            job_id=job.pk, generation=1
        )
        for _ in range(2):
            executor = MigrationExecutor(connection)
            executor.migrate(target)
            apps = executor.loader.project_state(target).apps
            assert not apps.get_model("nassav", "SharedWork").objects.exists()
            assert not apps.get_model("nassav", "UserOperation").objects.exists()
            assert (
                apps.get_model("nassav", "UserLibraryEntry")
                .objects.get(pk=entry.pk)
                .user_id
                == user.pk
            )
            assert (
                apps.get_model("nassav", "TaskJob").objects.get(pk=job.pk).owner_id
                == user.pk
            )
            assert (
                apps.get_model("nassav", "TaskAttempt")
                .objects.get(pk=attempt.pk)
                .generation
                == 1
            )
            MigrationExecutor(connection).migrate(previous)
    finally:
        MigrationExecutor(connection).migrate(latest)
