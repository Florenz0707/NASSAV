"""Durable reclamation intent and per-file evidence; never an automatic deletion trigger."""

from uuid import UUID, uuid4
from typing import TYPE_CHECKING
from django.db import models


class ResourceGcJob(models.Model):
    if TYPE_CHECKING:
        pool_id: UUID
        version_id: UUID | None
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    pool = models.ForeignKey("nassav.ResourcePoolEntry", on_delete=models.PROTECT)
    version = models.ForeignKey(
        "nassav.ResourceVersion", null=True, on_delete=models.PROTECT
    )
    pool_generation = models.PositiveBigIntegerField()
    active_key = models.CharField(max_length=128, null=True, unique=True)
    state = models.CharField(max_length=20, default="queued")
    revision = models.PositiveBigIntegerField(default=1)
    owner = models.UUIDField(null=True)
    lease_until = models.DateTimeField(null=True)
    error_code = models.CharField(max_length=64, default="")
    started_at = models.DateTimeField(null=True)
    finished_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "nassav_resource_gc_job"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(pool_generation__gte=1, revision__gte=1),
                name="resource_gc_positive_fences",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    state__in=[
                        "queued",
                        "deleting",
                        "cleanup_failed",
                        "completed",
                        "cancelled",
                    ]
                ),
                name="resource_gc_state",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(owner__isnull=True, lease_until__isnull=True)
                    | models.Q(owner__isnull=False, lease_until__isnull=False)
                ),
                name="resource_gc_owner_lease",
            ),
        ]
        indexes = [
            models.Index(
                fields=["state", "lease_until", "created_at"],
                name="resource_gc_dispatch_idx",
            )
        ]


class ResourceGcAsset(models.Model):
    job = models.ForeignKey(
        ResourceGcJob, on_delete=models.PROTECT, related_name="assets"
    )
    version = models.ForeignKey("nassav.ResourceVersion", on_delete=models.PROTECT)
    root = models.CharField(max_length=16)
    relative_path = models.CharField(max_length=512)
    kind = models.CharField(max_length=16)
    marker = models.UUIDField()
    sha256 = models.CharField(max_length=64)
    size = models.PositiveBigIntegerField()
    state = models.CharField(max_length=16, default="planned")
    fingerprint = models.JSONField(default=dict)
    error_code = models.CharField(max_length=64, default="")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "nassav_resource_gc_asset"
        constraints = [
            models.UniqueConstraint(
                fields=["job", "root", "relative_path"], name="resource_gc_asset_unique"
            ),
            models.CheckConstraint(
                condition=models.Q(state__in=["planned", "verified", "deleted"]),
                name="resource_gc_asset_state",
            ),
            models.CheckConstraint(
                condition=models.Q(root__in=["cover", "avatar", "video"], size__gte=1),
                name="resource_gc_asset_kind_size",
            ),
        ]
