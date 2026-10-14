"""Command expansion preserves old library/version/work/quota data on roundtrip."""

from uuid import uuid4

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_library_command_migration_preserves_existing_rows_without_auto_reservations():
    previous = [("nassav", "0045_version_pointer_fence")]
    target = [("nassav", "0046_library_commands_and_quota")]
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    try:
        executor.migrate(previous)
        apps = executor.loader.project_state(previous).apps
        user = apps.get_model("auth", "User").objects.create(
            username="library-command-migration"
        )
        pool = apps.get_model("nassav", "ResourcePoolEntry").objects.create(
            canonical_avid="CMD-046"
        )
        entry = apps.get_model("nassav", "UserLibraryEntry").objects.create(
            user_id=user.pk,
            pool_id=pool.pk,
            access_scope="public",
            desired_spec={"source": "jable"},
            version=4,
        )
        operation = apps.get_model("nassav", "UserOperation").objects.create(
            user_id=user.pk,
            pool_id=pool.pk,
            membership_id=entry.pk,
            kind="scrape",
            action="add",
            access_scope="public",
            request_id=uuid4(),
            request_hash="b" * 40,
            projected_work_version=9,
            version=3,
        )
        quota = apps.get_model("nassav", "QuotaReservation").objects.create(
            user_id=user.pk,
            pool_id=pool.pk,
            request_id=uuid4(),
            amount_bytes=123,
            state="held",
        )
        for _ in range(2):
            executor = MigrationExecutor(connection)
            executor.migrate(target)
            apps = executor.loader.project_state(target).apps
            row = apps.get_model("nassav", "UserOperation").objects.get(pk=operation.pk)
            assert row.quota_reservation_id is None and row.demand_generation == 1
            assert (
                row.progress == {}
                and row.timeline == []
                and row.projected_work_version == 9
            )
            assert (
                apps.get_model("nassav", "UserLibraryEntry")
                .objects.get(pk=entry.pk)
                .demand_generations
                == {}
            )
            assert (
                apps.get_model("nassav", "QuotaReservation")
                .objects.get(pk=quota.pk)
                .amount_bytes
                == 123
            )
            assert not apps.get_model("nassav", "UserLibraryCommand").objects.exists()
            row.quota_reservation_id = quota.pk
            row.save()
            apps.get_model("nassav", "UserLibraryCommand").objects.create(
                user_id=user.pk,
                entry_id=entry.pk,
                request_id=uuid4(),
                action="release",
                payload_hash="a" * 40,
                result={"released": True},
            )
            MigrationExecutor(connection).migrate(previous)
            old = MigrationExecutor(connection).loader.project_state(previous).apps
            assert (
                old.get_model("nassav", "UserLibraryEntry")
                .objects.get(pk=entry.pk)
                .version
                == 4
            )
            assert (
                old.get_model("nassav", "UserOperation")
                .objects.get(pk=operation.pk)
                .version
                == 3
            )
            assert (
                old.get_model("nassav", "QuotaReservation")
                .objects.get(pk=quota.pk)
                .state
                == "held"
            )
    finally:
        MigrationExecutor(connection).migrate(latest)
