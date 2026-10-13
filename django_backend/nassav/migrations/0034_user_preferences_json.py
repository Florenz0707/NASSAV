"""Preserve all six legacy values; schema evolution uses frozen historical rules."""

from django.db import migrations, models
from django.utils import timezone

LEGACY_DEFAULTS = {
    "enable_avatar": "true",
    "display_title": "source_title",
    "font_family": "Mplus2",
    "color_mode": "dark",
    "search_result_display_style": "grid",
    "default_external_search_source": "jable",
}


def forwards(apps, schema_editor):
    Preferences = apps.get_model("nassav", "UserPreferences")
    alias = schema_editor.connection.alias
    for row in Preferences.objects.using(alias).all().iterator(chunk_size=500):
        Preferences.objects.using(alias).filter(pk=row.pk).update(
            preferences={key: getattr(row, key) for key in LEGACY_DEFAULTS}
        )


def backwards(apps, schema_editor):
    Preferences = apps.get_model("nassav", "UserPreferences")
    alias = schema_editor.connection.alias
    for row in Preferences.objects.using(alias).all().iterator(chunk_size=500):
        stored = row.preferences if isinstance(row.preferences, dict) else {}
        values = {}
        for key, default in LEGACY_DEFAULTS.items():
            value = stored.get(key, default)
            # Old varchar columns cannot represent future JSON types or arbitrarily long values.
            limit = (
                100
                if key == "font_family"
                else {
                    "enable_avatar": 5,
                    "color_mode": 5,
                    "display_title": 32,
                    "search_result_display_style": 16,
                    "default_external_search_source": 50,
                }[key]
            )
            values[key] = (
                value if isinstance(value, str) and len(value) <= limit else default
            )
        Preferences.objects.using(alias).filter(pk=row.pk).update(**values)


class Migration(migrations.Migration):
    dependencies = [("nassav", "0033_personal_resource_state_and_preferences")]
    operations = [
        migrations.AddField(
            model_name="userpreferences",
            name="preferences",
            field=models.JSONField(default=dict),
        ),
        migrations.AddField(
            model_name="userpreferences",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True, default=timezone.now),
            preserve_default=False,
        ),
        migrations.RunPython(forwards, backwards),
        *[
            migrations.RemoveField(model_name="userpreferences", name=key)
            for key in LEGACY_DEFAULTS
        ],
        migrations.RemoveField(model_name="userpreferences", name="legacy_imported_at"),
    ]
