"""Publication CAS adds a default base revision without losing ready versions/pins."""

from datetime import timedelta
from uuid import uuid4

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone


@pytest.mark.django_db(transaction=True)
def test_pointer_fence_migration_keeps_version_manifest_membership_and_reader():
    previous = [("nassav", "0044_resource_version_ledger")]
    target = [("nassav", "0045_version_pointer_fence")]
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    try:
        executor.migrate(previous)
        apps = executor.loader.project_state(previous).apps
        user = apps.get_model("auth", "User").objects.create(
            username="pointer-migration"
        )
        resource = apps.get_model("nassav", "AVResource").objects.create(avid="PTR-045")
        pool = apps.get_model("nassav", "ResourcePoolEntry").objects.create(
            canonical_avid="PTR-045", resource_id=resource.pk, state="ready"
        )
        version = apps.get_model("nassav", "ResourceVersion").objects.create(
            pool_id=pool.pk,
            pool_generation=1,
            kind="metadata",
            source_name="jable",
            access_scope="public",
            context_revision="fixture",
            state="ready",
            published_at=timezone.now(),
            metadata={"source_title": "existing snapshot"},
            manifest=[{"fixture": "no physical file"}],
        )
        entry = apps.get_model("nassav", "UserLibraryEntry").objects.create(
            user_id=user.pk,
            pool_id=pool.pk,
            state="active",
            access_scope="public",
            current_version_id=version.pk,
            desired_spec={"source": "jable"},
        )
        pointer = apps.get_model("nassav", "ResourceVersionPointer").objects.create(
            pool_id=pool.pk,
            kind="metadata",
            source_name="jable",
            access_scope="public",
            current_id=version.pk,
            revision=4,
        )
        lease = apps.get_model("nassav", "ResourceReadLease").objects.create(
            user_id=user.pk,
            version_id=version.pk,
            request_id=uuid4(),
            login_hash="fixture",
            expires_at=timezone.now() + timedelta(seconds=30),
            absolute_expires_at=timezone.now() + timedelta(seconds=60),
        )
        for _ in range(2):
            executor = MigrationExecutor(connection)
            executor.migrate(target)
            apps = executor.loader.project_state(target).apps
            row = apps.get_model("nassav", "ResourceVersion").objects.get(pk=version.pk)
            assert row.base_pointer_revision == 1 and row.state == "ready"
            assert row.metadata == {"source_title": "existing snapshot"}
            assert row.manifest == [{"fixture": "no physical file"}]
            assert (
                apps.get_model("nassav", "UserLibraryEntry")
                .objects.get(pk=entry.pk)
                .current_version_id
                == version.pk
            )
            assert (
                apps.get_model("nassav", "ResourceReadLease")
                .objects.get(pk=lease.pk)
                .version_id
                == version.pk
            )
            assert (
                apps.get_model("nassav", "ResourceVersionPointer")
                .objects.get(pk=pointer.pk)
                .revision
                == 4
            )
            row.base_pointer_revision = 4
            row.save()
            MigrationExecutor(connection).migrate(previous)
    finally:
        MigrationExecutor(connection).migrate(latest)
