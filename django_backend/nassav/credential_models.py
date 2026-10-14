"""Encrypted source credentials and versioned refresh contexts."""

from typing import TYPE_CHECKING
from uuid import uuid4

from django.conf import settings
from django.db import models
from django.utils import timezone


class SourceCredentialKeyPolicy(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    active_key_id = models.CharField(max_length=64)
    version = models.PositiveBigIntegerField(default=1)
    updated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "nassav_source_credential_key_policy"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(id=1, version__gte=1),
                name="source_key_policy_singleton",
            )
        ]


class SourceCredential(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    source_name = models.CharField(max_length=50)
    scope = models.CharField(
        max_length=16, choices=[("system", "system"), ("personal", "personal")]
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT
    )
    origin_host = models.CharField(max_length=253)
    kind = models.CharField(
        max_length=16, choices=[("clearance", "clearance"), ("account", "account")]
    )
    state = models.CharField(
        max_length=16,
        default="active",
        choices=[
            ("active", "active"),
            ("quarantined", "quarantined"),
            ("revoked", "revoked"),
        ],
    )
    ciphertext = models.TextField(default="")
    key_id = models.CharField(max_length=64, default="")
    version = models.PositiveBigIntegerField(default=1)
    revoked_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)

    if TYPE_CHECKING:
        owner_id: int | None

    class Meta:
        db_table = "nassav_source_credential"
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(scope="system", owner__isnull=True)
                    | models.Q(scope="personal", owner__isnull=False)
                ),
                name="source_cred_scope_owner",
            ),
            models.CheckConstraint(
                condition=models.Q(version__gte=1), name="source_cred_positive_version"
            ),
            models.UniqueConstraint(
                fields=["source_name"],
                condition=models.Q(scope="system"),
                name="source_cred_system_unique",
            ),
            models.UniqueConstraint(
                fields=["owner", "source_name"],
                condition=models.Q(scope="personal"),
                name="source_cred_personal_unique",
            ),
        ]


class SourceSessionSnapshot(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    credential = models.ForeignKey(SourceCredential, on_delete=models.PROTECT)
    credential_version = models.PositiveBigIntegerField()
    origin_host = models.CharField(max_length=253)
    egress_profile = models.CharField(max_length=64)
    browser_context = models.CharField(max_length=64)
    ciphertext = models.TextField(default="")
    key_id = models.CharField(max_length=64, default="")
    version = models.PositiveBigIntegerField(default=1)
    generation = models.PositiveBigIntegerField(default=1)
    refresh_owner = models.UUIDField(null=True)
    lease_until = models.DateTimeField(null=True)
    expires_at = models.DateTimeField(null=True)
    verified_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)

    if TYPE_CHECKING:
        credential_id: object

    class Meta:
        db_table = "nassav_source_session_snapshot"
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "credential",
                    "credential_version",
                    "origin_host",
                    "egress_profile",
                    "browser_context",
                ],
                name="source_session_context_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    version__gte=1, generation__gte=1, credential_version__gte=1
                ),
                name="source_session_positive_versions",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(refresh_owner__isnull=True, lease_until__isnull=True)
                    | models.Q(refresh_owner__isnull=False, lease_until__isnull=False)
                ),
                name="source_session_lease_pair",
            ),
        ]
