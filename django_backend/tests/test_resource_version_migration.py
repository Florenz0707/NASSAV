"""Version ledger adds no guessed ownership/publication; old data survives reversal."""

from uuid import uuid4

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone


@pytest.mark.django_db(transaction=True)
def test_version_migration_roundtrip_keeps_existing_resource_membership_and_work():
    previous = [("nassav", "0043_user_operation_projection")]
    target = [("nassav", "0044_resource_version_ledger")]
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    try:
        executor.migrate(previous)
        apps = executor.loader.project_state(previous).apps
        user = apps.get_model("auth", "User").objects.create(
            username="version-migration"
        )
        resource = apps.get_model("nassav", "AVResource").objects.create(
            avid="VER-044", source="jable"
        )
        pool = apps.get_model("nassav", "ResourcePoolEntry").objects.create(
            canonical_avid="VER-044", resource_id=resource.pk, state="ready"
        )
        entry = apps.get_model("nassav", "UserLibraryEntry").objects.create(
            user_id=user.pk,
            pool_id=pool.pk,
            state="active",
            version=3,
            desired_spec={"source": "jable"},
            access_scope=f"legacy:operator:{user.pk}",
        )
        job = apps.get_model("nassav", "TaskJob").objects.create(
            avid="VER-044", kind="scrape", action="add"
        )
        work = apps.get_model("nassav", "SharedWork").objects.create(
            pool_id=pool.pk,
            pool_generation=1,
            job_id=job.pk,
            spec_hash="a" * 64,
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
            projected_work_version=7,
            version=2,
        )
        apps.get_model("nassav", "WorkSubscription").objects.create(
            work_id=work.pk, operation_id=operation.pk
        )
        for _ in range(2):
            executor = MigrationExecutor(connection)
            executor.migrate(target)
            apps = executor.loader.project_state(target).apps
            Version = apps.get_model("nassav", "ResourceVersion")
            assert not Version.objects.exists()  # No fabricated immutable evidence.
            current = apps.get_model("nassav", "UserLibraryEntry").objects.get(
                pk=entry.pk
            )
            assert (
                current.current_version_id is None and current.video_version_id is None
            )
            assert (
                current.version == 3
                and current.access_scope == f"legacy:operator:{user.pk}"
            )
            version = Version.objects.create(
                pool_id=pool.pk,
                pool_generation=1,
                work_id=work.pk,
                owner_id=user.pk,
                kind="metadata",
                source_name="jable",
                access_scope=current.access_scope,
                context_revision="historical-fixture",
                state="ready",
                published_at=timezone.now(),
                metadata={"source_title": "historical title"},
                manifest=[],
            )
            current.current_version_id = version.pk
            current.save()
            apps.get_model("nassav", "ResourceVersionPointer").objects.create(
                pool_id=pool.pk,
                kind="metadata",
                source_name="jable",
                access_scope=current.access_scope,
                current_id=version.pk,
            )
            assert (
                apps.get_model("nassav", "UserOperation")
                .objects.get(pk=operation.pk)
                .projected_work_version
                == 7
            )
            assert (
                apps.get_model("nassav", "AVResource")
                .objects.get(pk=resource.pk)
                .source
                == "jable"
            )
            MigrationExecutor(connection).migrate(previous)
            old_apps = MigrationExecutor(connection).loader.project_state(previous).apps
            assert (
                old_apps.get_model("nassav", "UserLibraryEntry")
                .objects.get(pk=entry.pk)
                .version
                == 3
            )
            assert (
                old_apps.get_model("nassav", "WorkSubscription")
                .objects.get(operation_id=operation.pk)
                .work_id
                == work.pk
            )
    finally:
        MigrationExecutor(connection).migrate(latest)
