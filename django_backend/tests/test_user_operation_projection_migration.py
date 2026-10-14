"""Projection cursor is additive; user demand and shared identity survive rollback."""

from uuid import uuid4

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_projection_migration_preserves_existing_operation_and_subscription():
    previous = [("nassav", "0042_shared_work_subscriptions")]
    target = [("nassav", "0043_user_operation_projection")]
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    try:
        executor.migrate(previous)
        apps = executor.loader.project_state(previous).apps
        user = apps.get_model("auth", "User").objects.create(
            username="projection-migration"
        )
        pool = apps.get_model("nassav", "ResourcePoolEntry").objects.create(
            canonical_avid="PROJ-043"
        )
        entry = apps.get_model("nassav", "UserLibraryEntry").objects.create(
            user_id=user.pk,
            pool_id=pool.pk,
            access_scope="public",
            desired_spec={"source": "jable"},
        )
        job = apps.get_model("nassav", "TaskJob").objects.create(
            avid="PROJ-043",
            kind="scrape",
            action="add",
            state="running",
            version=12,
        )
        work = apps.get_model("nassav", "SharedWork").objects.create(
            pool_id=pool.pk,
            pool_generation=1,
            job_id=job.pk,
            spec_hash="a" * 64,
            spec={"source": "jable"},
            access_scope="public",
        )
        operation = apps.get_model("nassav", "UserOperation").objects.create(
            user_id=user.pk,
            pool_id=pool.pk,
            membership_id=entry.pk,
            request_id=uuid4(),
            request_hash="b" * 40,
            kind="scrape",
            action="add",
            access_scope="public",
            state="running",
            stage="metadata",
            version=3,
        )
        subscription = apps.get_model("nassav", "WorkSubscription").objects.create(
            operation_id=operation.pk,
            work_id=work.pk,
        )
        for _ in range(2):
            executor = MigrationExecutor(connection)
            executor.migrate(target)
            apps = executor.loader.project_state(target).apps
            row = apps.get_model("nassav", "UserOperation").objects.get(pk=operation.pk)
            assert row.projected_work_version == 0
            assert (
                row.user_id,
                row.membership_id,
                row.state,
                row.stage,
                row.version,
            ) == (
                user.pk,
                entry.pk,
                "running",
                "metadata",
                3,
            )
            row.projected_work_version = 12
            row.save()
            sub = apps.get_model("nassav", "WorkSubscription").objects.get(
                pk=subscription.pk
            )
            assert sub.work_id == work.pk and sub.state == "attached"
            MigrationExecutor(connection).migrate(previous)
    finally:
        MigrationExecutor(connection).migrate(latest)
