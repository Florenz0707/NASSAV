"""Scoped immutable publications and fixed-version reader pins."""

from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from django.conf import settings
from django.db import models


class ResourceVersion(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    pool = models.ForeignKey("nassav.ResourcePoolEntry", on_delete=models.PROTECT)
    pool_generation = models.PositiveBigIntegerField()
    work = models.OneToOneField(
        "nassav.SharedWork", null=True, on_delete=models.PROTECT
    )
    parent = models.ForeignKey("self", null=True, on_delete=models.PROTECT)
    base_pointer_revision = models.PositiveBigIntegerField(default=1)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT
    )
    kind = models.CharField(max_length=16)
    source_name = models.CharField(max_length=50)
    quality = models.CharField(max_length=16, default="best")
    access_scope = models.CharField(max_length=128)
    credential_refs = models.JSONField(default=dict)
    context_revision = models.CharField(max_length=256)
    state = models.CharField(max_length=16, default="staging")
    metadata = models.JSONField(default=dict)
    manifest = models.JSONField(default=list)
    file_size = models.PositiveBigIntegerField(default=0)
    media_identity = models.CharField(max_length=64, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    published_at = models.DateTimeField(null=True)

    if TYPE_CHECKING:
        pool_id: UUID
        work_id: UUID | None
        parent_id: UUID | None
        owner_id: int | None

    class Meta:
        db_table = "nassav_resource_version"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(pool_generation__gte=1),
                name="resource_version_generation",
            ),
            models.CheckConstraint(
                condition=models.Q(kind__in=["metadata", "video"]),
                name="resource_version_kind",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    state__in=[
                        "staging",
                        "ready",
                        "retired",
                        "reclaimed",
                        "quarantined",
                    ]
                ),
                name="resource_version_state",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(access_scope="public", owner__isnull=True)
                    | (~models.Q(access_scope="public") & models.Q(owner__isnull=False))
                ),
                name="resource_version_owner_scope",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(state="staging", published_at__isnull=True)
                    | (
                        ~models.Q(state="staging")
                        & models.Q(published_at__isnull=False)
                    )
                ),
                name="resource_version_publish_time",
            ),
        ]
        indexes = [
            models.Index(
                fields=["pool", "access_scope", "kind", "-created_at"],
                name="resource_version_scope_idx",
            )
        ]


class ResourceVersionPointer(models.Model):
    pool = models.ForeignKey("nassav.ResourcePoolEntry", on_delete=models.PROTECT)
    source_name = models.CharField(max_length=50)
    quality = models.CharField(max_length=16, default="best")
    access_scope = models.CharField(max_length=128)
    kind = models.CharField(max_length=16)
    current = models.ForeignKey(ResourceVersion, null=True, on_delete=models.PROTECT)
    revision = models.PositiveBigIntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)

    if TYPE_CHECKING:
        pool_id: UUID
        current_id: UUID | None

    class Meta:
        db_table = "nassav_resource_version_pointer"
        constraints = [
            models.UniqueConstraint(
                fields=["pool", "source_name", "quality", "access_scope", "kind"],
                name="resource_version_pointer_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(revision__gte=1), name="resource_pointer_revision"
            ),
            models.CheckConstraint(
                condition=models.Q(kind__in=["metadata", "video"]),
                name="resource_pointer_kind",
            ),
        ]


class ResourceReadLease(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    version = models.ForeignKey(ResourceVersion, on_delete=models.PROTECT)
    playback_session = models.ForeignKey(
        "nassav.PlaybackSession", null=True, on_delete=models.PROTECT
    )
    request_id = models.UUIDField()
    login_hash = models.CharField(max_length=64)
    account_epoch = models.PositiveBigIntegerField(default=0)
    state = models.CharField(max_length=16, default="active")
    revision = models.PositiveBigIntegerField(default=1)
    expires_at = models.DateTimeField()
    absolute_expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    if TYPE_CHECKING:
        user_id: int
        version_id: UUID
        playback_session_id: UUID | None

    class Meta:
        db_table = "nassav_resource_read_lease"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "request_id"], name="resource_read_request_unique"
            ),
            models.CheckConstraint(
                condition=models.Q(state__in=["active", "released"]),
                name="resource_read_state",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    revision__gte=1, expires_at__lte=models.F("absolute_expires_at")
                ),
                name="resource_read_deadline",
            ),
        ]
        indexes = [
            models.Index(
                fields=["version", "state", "expires_at"],
                name="resource_read_version_idx",
            )
        ]
