"""Owned catalog pages and safe authorized avatar addresses; no image filesystem I/O."""

import hashlib
from pathlib import PurePosixPath

from django.core.paginator import Paginator
from django.db.models import F, Q, Window
from django.db.models.functions import RowNumber

from nassav.catalog_entities import CatalogEntity
from nassav.catalog_models import UserCatalogLink
from nassav.catalog_projection import term_stats, own_term, name_key
from nassav.library_catalog import held_entries
from nassav.version_image_files import asset_identity


def avatar_urls(user_id, terms):
    ids = [term.pk for term in terms if term.kind == "actor"]
    if not ids:
        return {}
    links = (
        UserCatalogLink.objects.filter(
            term_id__in=ids,
            term__user_id=user_id,
            entry__user_id=user_id,
            entry_id__in=held_entries(user_id).values("pk"),
        )
        .filter(
            Q(version_id=F("entry__current_version_id"))
            | Q(version__isnull=True, entry__current_version__isnull=True)
        )
        .annotate(
            ordinal=Window(
                RowNumber(),
                partition_by=[F("term_id")],
                order_by=[F("entry__updated_at").desc(), F("pk").desc()],
            )
        )
        .filter(ordinal__lte=3)
        .select_related("term", "version", "entry__pool__resource")
    )
    links = list(links)
    from nassav.models import Actor

    legacy_resources = {
        link.entry.pool.resource_id for link in links if link.version_id is None
    }
    legacy = (
        {
            (row["resources__pk"], name_key(row["name"])): row["avatar_filename"]
            for row in Actor.objects.filter(resources__pk__in=legacy_resources).values(
                "resources__pk", "name", "avatar_filename"
            )
            if row["avatar_filename"]
        }
        if legacy_resources
        else {}
    )
    result = {}
    for link in links:
        if link.term_id in result:
            continue
        if link.version is not None:
            names = link.version.metadata.get("actors", [])
            hashes = {
                hashlib.sha256(name.encode()).hexdigest()
                for name in names
                if isinstance(name, str) and name_key(name) == link.term.name_key
            }
            for asset in link.version.manifest:
                if (
                    isinstance(asset, dict)
                    and asset.get("kind") == asset.get("root") == "avatar"
                    and isinstance(asset.get("path"), str)
                    and PurePosixPath(asset["path"]).stem in hashes
                ):
                    result[link.term_id] = (
                        f"/nassav/api/library/entries/{link.entry_id}/images/{asset_identity(asset)}"
                    )
                    break
        elif link.entry.pool.resource is not None:
            # Only explicit legacy ownership can reach this branch.
            filename = legacy.get((link.entry.pool.resource_id, link.term.name_key))
            if filename:
                result[link.term_id] = f"/nassav/api/actors/{link.term_id}/avatar"
    return result


def external_entity(user_id, kind, term_id):
    term = own_term(user_id, kind, term_id)
    return CatalogEntity(
        term.pk,
        term.name,
        term.resource_count,
        f"owned-catalog-v1:{term.name_key}",
        avatar_url=avatar_urls(user_id, [term]).get(term.pk),
    )


def list_terms(user_id, kind, params):
    rows = term_stats(user_id, kind)
    search = str(params.get("search", "")).strip()
    if search:
        rows = rows.filter(name__icontains=search)
    identifier = params.get("id")
    if identifier:
        try:
            rows = rows.filter(pk=int(identifier))
        except (ValueError, TypeError):
            raise ValueError("Invalid catalog identity") from None
    ordering, direction = params.get("order_by", "count"), params.get("order", "desc")
    if ordering not in {"name", "count"} or direction not in {"asc", "desc"}:
        raise ValueError("Invalid catalog ordering")
    field = "name" if ordering == "name" else "resource_count"
    rows = rows.order_by(("-" if direction == "desc" else "") + field, "name", "pk")
    try:
        page, size = int(params.get("page", 1)), int(params.get("page_size", 20))
    except (ValueError, TypeError):
        raise ValueError("Invalid pagination") from None
    if page < 1 or not 1 <= size <= 100:
        raise ValueError("Invalid pagination")
    pages = Paginator(rows, size)
    selected = pages.get_page(page)
    terms = list(selected.object_list)
    from nassav.recommendation.seed_profiles import (
        recommendation_seed_profile_repository,
    )

    profiles = recommendation_seed_profile_repository.for_user(user_id)
    blocked = profiles.get_blocked_normalized_values(
        seed_type=kind, values=[term.name for term in terms]
    )
    avatars = avatar_urls(user_id, terms)
    data = [
        {
            "id": term.pk,
            "name": term.name,
            "resource_count": term.resource_count,
            "avatar_url": avatars.get(term.pk),
            "avatar_filename": None,
            "is_blocked": profiles.normalize_value(term.name) in blocked,
            "source_mapping": None,
        }
        for term in terms
    ]
    return data, {
        "total": pages.count,
        "page": selected.number,
        "page_size": size,
        "pages": pages.num_pages,
    }
