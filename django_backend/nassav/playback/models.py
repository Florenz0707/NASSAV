"""DB-owned sessions; Celery IDs are transport, not playback state."""

from uuid import uuid4
from django.conf import settings
from django.db import models


class PlaybackSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    login_hash = models.CharField(max_length=64)
    resource = models.ForeignKey("nassav.AVResource", on_delete=models.CASCADE)
    media_kind = models.CharField(max_length=16, default="source")
    source = models.CharField(max_length=50)
    request_id = models.UUIDField()
    state = models.CharField(max_length=16, default="queued")
    version = models.PositiveIntegerField(default=1)
    generation = models.PositiveIntegerField(default=1)
    execution_id = models.UUIDField(default=uuid4)
    lease_until = models.DateTimeField(null=True)
    prepare_deadline = models.DateTimeField()
    dispatch_after = models.DateTimeField()
    descriptor = models.JSONField(default=dict)
    library_grant = models.JSONField(default=dict)
    history_sequence = models.PositiveIntegerField(default=0)
    history_recorded_at = models.DateTimeField(null=True)
    refresh_count = models.PositiveSmallIntegerField(default=0)
    manifest_identity = models.JSONField(default=dict)
    error_code = models.CharField(max_length=40, blank=True)
    last_command_id = models.UUIDField(null=True)
    last_seen_at = models.DateTimeField()
    idle_expires_at = models.DateTimeField()
    absolute_expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "nassav_playback_session"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "login_hash", "request_id"],
                name="playback_request_unique",
            )
        ]
        indexes = [
            models.Index(
                fields=["state", "dispatch_after"], name="playback_dispatch_idx"
            ),
            models.Index(fields=["absolute_expires_at"], name="playback_expiry_idx"),
        ]


class PlaybackProgress(models.Model):
    """Personal positions survive resource/session deletion; writer tokens do not."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    avid = models.CharField(max_length=50)
    media_key = models.CharField(max_length=64)
    media_kind = models.CharField(max_length=16)
    source = models.CharField(max_length=50, blank=True)
    position_seconds = models.FloatField(default=0)
    duration_seconds = models.FloatField(default=0)
    completed = models.BooleanField(default=False)
    version = models.PositiveIntegerField(default=1)
    writer_generation = models.PositiveIntegerField(default=0)
    writer_session = models.UUIDField(null=True)
    claim_id = models.UUIDField(null=True)
    last_sequence = models.PositiveIntegerField(default=0)
    last_payload = models.CharField(max_length=64, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "nassav_playback_progress"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "avid", "media_key"], name="playback_progress_unique"
            )
        ]
        indexes = [
            models.Index(
                fields=["user", "updated_at"], name="playback_progress_user_idx"
            )
        ]
