"""Private requests subscribe to DB-owned shared execution, never to Celery IDs."""

from uuid import uuid4
from typing import TYPE_CHECKING

from django.conf import settings
from django.db import models


class SharedWork(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    pool = models.ForeignKey(
        "nassav.ResourcePoolEntry", on_delete=models.PROTECT, related_name="shared_work"
    )
    pool_generation = models.PositiveBigIntegerField()
    job = models.OneToOneField(
        "nassav.TaskJob", on_delete=models.PROTECT, related_name="shared_work"
    )
    spec_hash = models.CharField(max_length=64)
    spec = models.JSONField(default=dict)
    access_scope = models.CharField(max_length=128)
    credential_refs = models.JSONField(default=dict)
    active_key = models.CharField(max_length=64, null=True, unique=True)
    last_projected_version = models.PositiveBigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    if TYPE_CHECKING:
        pool_id: object
        job_id: object

    class Meta:
        db_table = "nassav_shared_work"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(pool_generation__gte=1),
                name="shared_work_generation_positive",
            )
        ]
        indexes = [
            models.Index(
                fields=["pool", "spec_hash", "-created_at"],
                name="shared_work_pool_spec_idx",
            )
        ]


class UserOperation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    pool = models.ForeignKey(
        "nassav.ResourcePoolEntry", on_delete=models.PROTECT, related_name="operations"
    )
    membership = models.ForeignKey(
        "nassav.UserLibraryEntry", null=True, on_delete=models.SET_NULL
    )
    request_id = models.UUIDField()
    request_hash = models.CharField(max_length=64)
    kind = models.CharField(max_length=16)
    action = models.CharField(max_length=16)
    desired_spec = models.JSONField(default=dict)
    access_scope = models.CharField(max_length=128)
    state = models.CharField(max_length=16, default="queued")
    version = models.PositiveBigIntegerField(default=1)
    stage = models.CharField(max_length=40, default="queued")
    message = models.TextField(default="")
    error_code = models.CharField(max_length=40, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    finished_at = models.DateTimeField(null=True)

    if TYPE_CHECKING:
        user_id: int
        pool_id: object
        membership_id: object | None

    class Meta:
        db_table = "nassav_user_operation"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "request_id"], name="user_operation_request_unique"
            ),
            models.CheckConstraint(
                condition=models.Q(version__gte=1),
                name="user_operation_version_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    state__in=[
                        "queued",
                        "running",
                        "pausing",
                        "paused",
                        "cancelling",
                        "succeeded",
                        "failed",
                        "cancelled",
                    ]
                ),
                name="user_operation_state_valid",
            ),
        ]
        indexes = [
            models.Index(
                fields=["user", "state", "-created_at"],
                name="user_operation_owner_state_idx",
            )
        ]


class WorkSubscription(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    operation = models.OneToOneField(
        UserOperation, on_delete=models.PROTECT, related_name="subscription"
    )
    work = models.ForeignKey(
        SharedWork, on_delete=models.PROTECT, related_name="subscriptions"
    )
    state = models.CharField(max_length=16, default="attached")
    version = models.PositiveBigIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    detached_at = models.DateTimeField(null=True)

    if TYPE_CHECKING:
        work_id: object
        operation_id: object

    class Meta:
        db_table = "nassav_work_subscription"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(state__in=["attached", "detached", "completed"]),
                name="work_subscription_state_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(version__gte=1),
                name="work_subscription_version_positive",
            ),
        ]
        indexes = [
            models.Index(fields=["work", "state"], name="work_subscription_demand_idx")
        ]


class UserOperationCommand(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    operation = models.ForeignKey(UserOperation, on_delete=models.PROTECT)
    request_id = models.UUIDField()
    action = models.CharField(max_length=16)
    payload_hash = models.CharField(max_length=64)
    result = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "nassav_user_operation_command"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "request_id"], name="user_operation_command_unique"
            )
        ]
