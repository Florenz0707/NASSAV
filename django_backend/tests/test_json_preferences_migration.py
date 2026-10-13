import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone


@pytest.mark.django_db(transaction=True)
def test_json_migration_preserves_existing_values_and_roundtrip_relations():
    previous = [("nassav", "0033_personal_resource_state_and_preferences")]
    target = [("nassav", "0034_user_preferences_json")]
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    values = {
        "enable_avatar": "false",
        "display_title": "original_title",
        "font_family": "Custom Font",
        "color_mode": "light",
        "search_result_display_style": "masonry",
        "default_external_search_source": "missav",
    }
    try:
        executor.migrate(previous)
        apps = executor.loader.project_state(previous).apps
        user = apps.get_model("auth", "User").objects.create(username="json-migration")
        preferences = apps.get_model("nassav", "UserPreferences").objects.create(
            user_id=user.pk, legacy_imported_at=timezone.now(), **values
        )
        updated = preferences.updated_at
        resource = apps.get_model("nassav", "AVResource").objects.create(
            avid="JSON-034", watched=True
        )
        state = apps.get_model("nassav", "UserResourceState").objects.create(
            user_id=user.pk, resource_id=resource.pk, notes="kept"
        )
        for _ in range(2):
            executor = MigrationExecutor(connection)
            executor.migrate(target)
            apps = executor.loader.project_state(target).apps
            Preferences = apps.get_model("nassav", "UserPreferences")
            row = Preferences.objects.get(pk=preferences.pk)
            assert row.user_id == user.pk and row.preferences == values
            assert row.created_at is not None and row.updated_at == updated
            assert {f.name for f in Preferences._meta.fields} == {
                "id",
                "user",
                "preferences",
                "created_at",
                "updated_at",
            }
            assert (
                apps.get_model("nassav", "UserResourceState")
                .objects.get(pk=state.pk)
                .notes
                == "kept"
            )
            assert (
                apps.get_model("nassav", "AVResource")
                .objects.get(pk=resource.pk)
                .watched
            )
            # A newly added key cannot be represented by the old six-column schema.
            Preferences.objects.filter(pk=row.pk).update(
                preferences={**values, "future": True}
            )
            executor = MigrationExecutor(connection)
            executor.migrate(previous)
            apps = executor.loader.project_state(previous).apps
            old = apps.get_model("nassav", "UserPreferences").objects.get(
                pk=preferences.pk
            )
            assert {key: getattr(old, key) for key in values} == values
            assert old.legacy_imported_at is None
            assert old.updated_at == updated
    finally:
        MigrationExecutor(connection).migrate(latest)
