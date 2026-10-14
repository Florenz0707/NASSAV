"""Shared resource identity and private membership; no automatic asset reclamation."""

from uuid import UUID, uuid4
from typing import TYPE_CHECKING

from django.conf import settings
from django.db import models

if TYPE_CHECKING:
    from django.db.models.fields.related_descriptors import RelatedManager


class ResourcePoolEntry(models.Model):
    if TYPE_CHECKING:
        resource_id: int | None
        memberships: "RelatedManager[UserLibraryEntry]"

    STATES = (
        "preparing",
        "ready",
        "pending_gc",
        "deleting",
        "cleanup_failed",
        "reclaimed",
    )
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    canonical_avid = models.CharField(max_length=50, unique=True)
    is_available = models.BooleanField(default=True)
    resource = models.OneToOneField(
        "nassav.AVResource",
        null=True,
        on_delete=models.SET_NULL,
        related_name="pool_entry",
    )
    state = models.CharField(max_length=20, default="preparing")
    lifetime_generation = models.PositiveBigIntegerField(default=1)
    version = models.PositiveBigIntegerField(default=1)
    gc_after = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "nassav_resource_pool_entry"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    state__in=[
                        "preparing",
                        "ready",
                        "pending_gc",
                        "deleting",
                        "cleanup_failed",
                        "reclaimed",
                    ]
                ),
                name="nassav_pool_state_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(version__gte=1, lifetime_generation__gte=1),
                name="nassav_pool_fences_positive",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(state="pending_gc", gc_after__isnull=False)
                    | (~models.Q(state="pending_gc") & models.Q(gc_after__isnull=True))
                ),
                name="nassav_pool_gc_deadline_valid",
            ),
        ]
        indexes = [
            models.Index(fields=["state", "gc_after"], name="nassav_pool_gc_idx")
        ]


class UserLibraryEntry(models.Model):
    if TYPE_CHECKING:
        pool_id: UUID

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    pool = models.ForeignKey(
        ResourcePoolEntry, on_delete=models.PROTECT, related_name="memberships"
    )
    state = models.CharField(max_length=16, default="pending")
    current_version = models.ForeignKey(
        "nassav.ResourceVersion",
        null=True,
        on_delete=models.PROTECT,
        related_name="metadata_holders",
    )
    video_version = models.ForeignKey(
        "nassav.ResourceVersion",
        null=True,
        on_delete=models.PROTECT,
        related_name="video_holders",
    )
    desired_spec = models.JSONField(default=dict)
    demand_generations = models.JSONField(default=dict)
    access_scope = models.CharField(max_length=128)
    version = models.PositiveBigIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "nassav_user_library_entry"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "pool"], name="nassav_library_user_pool_unique"
            ),
            models.CheckConstraint(
                condition=models.Q(state__in=["pending", "active"]),
                name="nassav_library_state_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(version__gte=1),
                name="nassav_library_version_positive",
            ),
        ]
        indexes = [
            models.Index(
                fields=["user", "state", "-created_at"],
                name="nassav_library_user_state_idx",
            )
        ]


class UserLibraryCommand(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    request_id = models.UUIDField()
    entry_id = models.UUIDField()
    action = models.CharField(max_length=16)
    payload_hash = models.CharField(max_length=64)
    result = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "nassav_user_library_command"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "request_id"], name="user_library_command_unique"
            )
        ]
