"""Run on SQLite and an isolated PostgreSQL instance, never the production DB."""

from uuid import uuid4
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone
import pytest

pytestmark = pytest.mark.django_db(transaction=True)


def test_refresh_migration_preserves_session_user_resource_and_is_reversible():
    old, new = ("nassav", "0029_playbacksession"), ("nassav", "0030_playback_refresh")
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    try:
        executor.migrate([old])
        apps = executor.loader.project_state([old]).apps
        user = apps.get_model("auth", "User").objects.create(
            username="playback-migration"
        )
        resource = apps.get_model("nassav", "AVResource").objects.create(
            avid="MIG-1", source="Jable"
        )
        now, request = timezone.now(), uuid4()
        row = apps.get_model("nassav", "PlaybackSession").objects.create(
            user_id=user.pk,
            resource_id=resource.pk,
            login_hash="binding",
            source="jable",
            request_id=request,
            prepare_deadline=now,
            dispatch_after=now,
            last_seen_at=now,
            idle_expires_at=now,
            absolute_expires_at=now,
            version=7,
            generation=2,
        )
        for target in [new, old, new]:
            executor = MigrationExecutor(connection)
            executor.migrate([target])
            models = executor.loader.project_state([target]).apps
            saved = models.get_model("nassav", "PlaybackSession").objects.get(pk=row.pk)
            assert saved.user_id == user.pk and saved.resource_id == resource.pk
            assert (
                saved.request_id == request
                and saved.version == 7
                and saved.generation == 2
            )
            assert (
                models.get_model("nassav", "AVResource")
                .objects.get(pk=resource.pk)
                .avid
                == "MIG-1"
            )
            if target == new:
                assert saved.refresh_count == 0 and saved.manifest_identity == {}
    finally:
        MigrationExecutor(connection).migrate(latest)
