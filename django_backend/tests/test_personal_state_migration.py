import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_personal_migration_reversible_preserves_shared_flags_and_relations():
    previous = [("nassav", "0032_playbackprogress")]
    target = [("nassav", "0033_personal_resource_state_and_preferences")]
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    try:
        executor.migrate(previous)
        apps = executor.loader.project_state(previous).apps
        resource = apps.get_model("nassav", "AVResource").objects.create(
            avid="TEST-033", watched=True, is_favorite=True
        )
        actor = apps.get_model("nassav", "Actor").objects.create(name="Migration Actor")
        resource.actors.add(actor)
        user = apps.get_model("auth", "User").objects.create(
            username="personal-migration"
        )
        for _ in range(2):
            executor = MigrationExecutor(connection)
            executor.migrate(target)
            apps = executor.loader.project_state(target).apps
            Resource = apps.get_model("nassav", "AVResource")
            loaded = Resource.objects.get(pk=resource.pk)
            assert loaded.watched and loaded.is_favorite
            assert list(loaded.actors.values_list("pk", flat=True)) == [actor.pk]
            State = apps.get_model("nassav", "UserResourceState")
            Preferences = apps.get_model("nassav", "UserPreferences")
            assert (
                not State.objects.exists()
            )  # Ownership is explicit, never guessed by schema migration.
            State.objects.create(
                user_id=user.pk, resource_id=resource.pk, notes="personal"
            )
            Preferences.objects.create(user_id=user.pk, color_mode="light")
            assert State.objects.get(user_id=user.pk).notes == "personal"
            assert Preferences.objects.get(user_id=user.pk).color_mode == "light"
            executor = MigrationExecutor(connection)
            executor.migrate(previous)
            assert (
                "nassav_user_resource_state"
                not in connection.introspection.table_names()
            )
    finally:
        MigrationExecutor(connection).migrate(latest)
