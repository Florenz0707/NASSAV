"""Database-owned JSON overrides; GET never writes defaults or cleans stored keys."""

from django.db import transaction

from nassav.db_retry import retry_sqlite_contention
from nassav.personal_models import UserPreferences
from nassav.personal_state import lock_user
from nassav.preference_definitions import effective_preferences, validate_preferences


def read_preferences(user_id):
    row = UserPreferences.objects.filter(user_id=user_id).first()
    return effective_preferences(row.preferences if row else {})


@retry_sqlite_contention
def update_preferences(user_id, changes):
    validate_preferences(changes)
    if not changes:
        return read_preferences(user_id)
    with transaction.atomic():
        lock_user(user_id)
        row, created = UserPreferences.objects.get_or_create(user_id=user_id)
        stored = row.preferences if isinstance(row.preferences, dict) else {}
        merged = {**stored, **changes}
        changed = created or any(
            key not in stored
            or type(stored[key]) is not type(value)
            or stored[key] != value
            for key, value in changes.items()
        )
        if changed:
            row.preferences = merged
            row.save(update_fields=["preferences", "updated_at"])
        return effective_preferences(row.preferences)
