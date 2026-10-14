"""Explicit application roles, safe audit, quota reservations and login bindings."""

from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from django.conf import settings
from django.db import models


class UserAccount(models.Model):
    if TYPE_CHECKING:
        user_id: int

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    role = models.CharField(max_length=16, default="user")
    version = models.PositiveBigIntegerField(default=1)
    storage_quota_bytes = models.PositiveBigIntegerField(null=True)
    max_active_operations = models.PositiveIntegerField(default=2)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "nassav_user_account"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(role__in=["user", "admin"]),
                name="nassav_account_role_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(version__gte=1, max_active_operations__gte=1),
                name="nassav_account_fences_valid",
            ),
        ]


class AccountControl(models.Model):
    """A single durable fence serializes last-admin checks and role changes."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1)
    version = models.PositiveBigIntegerField(default=1)

    class Meta:
        db_table = "nassav_account_control"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(id=1, version__gte=1),
                name="nassav_account_control_valid",
            )
        ]


class AuditEvent(models.Model):
    if TYPE_CHECKING:
        actor_id: int

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    request_id = models.UUIDField()
    action = models.CharField(max_length=64)
    object_id = models.CharField(max_length=64)
    reason = models.CharField(max_length=32)
    payload_hash = models.CharField(max_length=64)
    result = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "nassav_audit_event"
        constraints = [
            models.UniqueConstraint(
                fields=["actor", "request_id"], name="nassav_audit_command_unique"
            )
        ]
        indexes = [
            models.Index(fields=["-created_at", "id"], name="nassav_audit_time_idx")
        ]


class UserLoginSession(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    session = models.OneToOneField(
        "sessions.Session", on_delete=models.CASCADE, primary_key=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "nassav_user_login_session"


class AdminCommandReceipt(models.Model):
    """Minimal idempotency ledger retained independently of bounded audit history."""

    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    request_id = models.UUIDField()
    payload_hash = models.CharField(max_length=64)
    result = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "nassav_admin_command_receipt"
        constraints = [
            models.UniqueConstraint(
                fields=["actor", "request_id"], name="nassav_admin_receipt_unique"
            )
        ]


class QuotaReservation(models.Model):
    if TYPE_CHECKING:
        pool_id: UUID

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    pool = models.ForeignKey("nassav.ResourcePoolEntry", on_delete=models.PROTECT)
    request_id = models.UUIDField()
    amount_bytes = models.PositiveBigIntegerField()
    state = models.CharField(max_length=16, default="held")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "nassav_quota_reservation"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "request_id"], name="nassav_quota_request_unique"
            ),
            models.CheckConstraint(
                condition=models.Q(state__in=["held", "released"]),
                name="nassav_quota_state_valid",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "state"], name="nassav_quota_user_state_idx")
        ]
