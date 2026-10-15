"""Cursor rollback repeats discovery safely; it never discards GC authority."""

from uuid import uuid4
import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_gc_cursor_upgrade_reverse_upgrade_keeps_jobs_and_pool_state():
    old = [("nassav", "0050_resource_gc_ledger")]
    new = [("nassav", "0051_gc_discovery_cursor")]
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    try:
        executor.migrate(old)
        apps = executor.loader.project_state(old).apps
        pool = apps.get_model("nassav", "ResourcePoolEntry").objects.create(
            canonical_avid="SCAN-051"
        )
        job = apps.get_model("nassav", "ResourceGcJob").objects.create(
            pool_id=pool.pk, pool_generation=1, active_key="scan-fixture"
        )
        for _ in range(2):
            executor = MigrationExecutor(connection)
            executor.migrate(new)
            apps = executor.loader.project_state(new).apps
            assert not apps.get_model("nassav", "ResourceGcCursor").objects.exists()
            apps.get_model("nassav", "ResourceGcCursor").objects.create(
                pk=1, version_after=uuid4(), pool_after=pool.pk, revision=5
            )
            assert (
                apps.get_model("nassav", "ResourceGcJob").objects.get(pk=job.pk).state
                == "queued"
            )
            executor = MigrationExecutor(connection)
            executor.migrate(old)
            apps = executor.loader.project_state(old).apps
            assert (
                apps.get_model("nassav", "ResourcePoolEntry")
                .objects.get(pk=pool.pk)
                .lifetime_generation
                == 1
            )
            assert (
                apps.get_model("nassav", "ResourceGcJob")
                .objects.get(pk=job.pk)
                .revision
                == 1
            )
    finally:
        MigrationExecutor(connection).migrate(latest)
