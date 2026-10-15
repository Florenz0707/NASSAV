"""Personal state is independent of shared source facts and application configuration."""

from django.conf import settings
from django.db import models


class UserResourceState(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    resource = models.ForeignKey(
        "nassav.AVResource", on_delete=models.CASCADE, related_name="user_states"
    )
    watched = models.BooleanField(default=False)
    is_favorite = models.BooleanField(default=False)
    watch_later = models.BooleanField(default=False)
    watch_later_added_at = models.DateTimeField(null=True)
    notes = models.TextField(default="", blank=True)
    version = models.PositiveIntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "nassav_user_resource_state"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "resource"], name="nassav_user_resource_unique"
            )
        ]
        indexes = [
            models.Index(
                fields=["user", "is_favorite"], name="nassav_user_favorite_idx"
            ),
            models.Index(fields=["user", "watched"], name="nassav_user_watched_idx"),
        ]


class UserPreferences(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    preferences = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "nassav_user_preferences"


class UserWatchHistory(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    resource = models.ForeignKey(
        "nassav.AVResource", null=True, on_delete=models.SET_NULL
    )
    pool = models.ForeignKey("nassav.ResourcePoolEntry", on_delete=models.PROTECT)
    snapshot = models.JSONField(default=dict)
    last_watched_at = models.DateTimeField()
    media_kind = models.CharField(max_length=16)

    class Meta:
        db_table = "nassav_user_watch_history"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "pool"], name="nassav_user_history_unique"
            )
        ]
        indexes = [
            models.Index(
                fields=["user", "-last_watched_at", "-id"],
                name="nassav_user_history_idx",
            )
        ]
