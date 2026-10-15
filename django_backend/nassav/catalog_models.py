"""User-owned taxonomy projects authorized facts without global private aliases."""

from typing import TYPE_CHECKING
from uuid import UUID
from django.conf import settings
from django.db import models


class UserCatalogTerm(models.Model):
    if TYPE_CHECKING:
        user_id: int
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    kind = models.CharField(max_length=16)
    name = models.CharField(max_length=256)
    name_key = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "nassav_user_catalog_term"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "kind", "name_key"], name="user_catalog_term_unique"
            ),
            models.CheckConstraint(
                condition=models.Q(kind__in=["actor", "genre"]),
                name="user_catalog_kind_valid",
            ),
        ]


class UserCatalogLink(models.Model):
    if TYPE_CHECKING:
        entry_id: UUID
        version_id: UUID | None
        term_id: int
    entry = models.ForeignKey(
        "nassav.UserLibraryEntry",
        on_delete=models.CASCADE,
        related_name="catalog_links",
    )
    term = models.ForeignKey(
        UserCatalogTerm, on_delete=models.CASCADE, related_name="links"
    )
    version = models.ForeignKey(
        "nassav.ResourceVersion", null=True, on_delete=models.PROTECT
    )

    class Meta:
        db_table = "nassav_user_catalog_link"
        constraints = [
            models.UniqueConstraint(
                fields=["entry", "term"], name="user_catalog_link_unique"
            )
        ]
