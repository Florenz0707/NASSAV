"""Durable task control records; Redis leases remain execution-scoped."""

from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from django.conf import settings
from django.db import models

if TYPE_CHECKING:
    from django.db.models.fields.related_descriptors import RelatedManager


class TaskJob(models.Model):
    if TYPE_CHECKING:
        owner_id: int | None
        attempts: RelatedManager["TaskAttempt"]
        commands: RelatedManager["TaskCommand"]
        artifacts: RelatedManager["TaskArtifact"]

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    kind = models.CharField(max_length=16)
    avid = models.CharField(max_length=50)
    action = models.CharField(max_length=16)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL
    )
    active_key = models.CharField(max_length=80, null=True, unique=True)
    state = models.CharField(max_length=16, default="queued")
    requested_action = models.CharField(max_length=16, blank=True)
    stage = models.CharField(max_length=40, blank=True)
    version = models.PositiveBigIntegerField(default=1)
    generation = models.PositiveIntegerField(default=1)
    options = models.JSONField(default=dict)
    checkpoint = models.JSONField(default=dict)
    timeline = models.JSONField(default=list)
    resource_saved = models.BooleanField(default=False)
    translation = models.JSONField(default=dict)
    error_code = models.CharField(max_length=40, blank=True)
    message = models.TextField(blank=True)
    cleanup_state = models.CharField(max_length=16, default="not_required")
    cleanup_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True)

    class Meta:
        indexes = [models.Index(fields=["owner", "state", "created_at"])]


class TaskAttempt(models.Model):
    if TYPE_CHECKING:
        job_id: UUID

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    job = models.ForeignKey(TaskJob, related_name="attempts", on_delete=models.CASCADE)
    generation = models.PositiveIntegerField()
    role = models.CharField(max_length=16, default="main")
    state = models.CharField(max_length=16, default="pending")
    execution_owner = models.UUIDField(null=True)
    execution_identity = models.JSONField(default=dict)
    dispatch_error = models.TextField(blank=True)
    dispatched_at = models.DateTimeField(null=True)
    started_at = models.DateTimeField(null=True)
    heartbeat_at = models.DateTimeField(null=True)
    stopped_at = models.DateTimeField(null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["job", "generation", "role"],
                name="task_attempt_generation_role",
            )
        ]
        indexes = [models.Index(fields=["state", "dispatched_at"])]


class TaskArtifact(models.Model):
    if TYPE_CHECKING:
        job_id: UUID

    job = models.ForeignKey(TaskJob, related_name="artifacts", on_delete=models.CASCADE)
    root = models.CharField(max_length=16)
    relative_path = models.CharField(max_length=512)
    kind = models.CharField(max_length=24)
    state = models.CharField(max_length=16, default="staged")
    size = models.PositiveBigIntegerField(null=True)
    sha256 = models.CharField(max_length=64, blank=True)
    target_path = models.CharField(max_length=512, blank=True)
    details = models.JSONField(default=dict)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["job", "root", "relative_path"], name="task_artifact_owned_path"
            )
        ]


class TaskCommand(models.Model):
    job = models.ForeignKey(TaskJob, related_name="commands", on_delete=models.CASCADE)
    request_id = models.UUIDField()
    action = models.CharField(max_length=16)
    version = models.PositiveBigIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["job", "request_id"], name="task_command_request_id"
            )
        ]


class TaskAssetTarget(models.Model):
    """A publication epoch protects recovery from overwriting a later commit."""

    root = models.CharField(max_length=16)
    relative_path = models.CharField(max_length=512)
    marker = models.UUIDField(default=uuid4)
    sha256 = models.CharField(max_length=64, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["root", "relative_path"], name="task_asset_target_path"
            )
        ]
