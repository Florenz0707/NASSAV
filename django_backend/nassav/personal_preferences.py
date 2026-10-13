"""Database-owned general preferences; no runtime file or process cache."""

from django.db import models, transaction

from nassav.db_retry import retry_sqlite_contention
from nassav.personal_models import UserPreferences
from nassav.personal_state import lock_user

DEFAULT_PREFERENCES = {
    "enable_avatar": "true",
    "display_title": "source_title",
    "font_family": "Mplus2",
    "color_mode": "dark",
    "search_result_display_style": "grid",
    "default_external_search_source": "jable",
}
PREFERENCE_CHOICES = {
    "enable_avatar": {"true", "false"},
    "display_title": {"original_title", "source_title", "translated_title"},
    "color_mode": {"light", "dark"},
    "search_result_display_style": {"grid", "masonry"},
}


def validate_preferences(changes):
    for key, value in changes.items():
        if (
            key not in DEFAULT_PREFERENCES
            or not isinstance(value, str)
            or not value.strip()
        ):
            raise ValueError(f"无效的设置项: {key}")
        if key in PREFERENCE_CHOICES and value not in PREFERENCE_CHOICES[key]:
            raise ValueError(f"无效的设置值: {key}")
        field = UserPreferences._meta.get_field(key)
        assert isinstance(field, models.CharField)
        limit = field.max_length
        if limit is not None and len(value) > limit:
            raise ValueError(f"设置值过长: {key}")


def read_preferences(user_id):
    row = UserPreferences.objects.filter(user_id=user_id).first()
    return {
        key: getattr(row, key) if row else value
        for key, value in DEFAULT_PREFERENCES.items()
    }


@retry_sqlite_contention
def update_preferences(user_id, changes):
    validate_preferences(changes)
    with transaction.atomic():
        lock_user(user_id)
        row, _ = UserPreferences.objects.get_or_create(user_id=user_id)
        for key, value in changes.items():
            setattr(row, key, value)
        row.save(update_fields=[*changes, "updated_at"])
        return read_preferences(user_id)
