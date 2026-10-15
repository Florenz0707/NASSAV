"""Current owned taxonomy and preference counts; no network or global entity writes."""

import hashlib
from datetime import timedelta

from django.db import connection
from django.db.models import Count, F, Q, FilteredRelation
from django.utils import timezone

from nassav.catalog_models import UserCatalogTerm, UserCatalogLink
from nassav.library_catalog import held_entries, metadata
from nassav.library_membership import LibraryNotFound
from nassav.recommendation.seed_policy import normalize_seed_value


def name_key(name):
    return hashlib.sha256(normalize_seed_value(name).encode()).hexdigest()


def sync_entry(entry):
    """Caller holds user -> pool fence; do not call from system pool publication."""
    if not connection.in_atomic_block:
        raise RuntimeError("Catalog synchronization requires membership transaction")
    pairs = {}
    if entry.state == "active":
        snapshot = metadata(entry)
        for kind, field in (("actor", "actors"), ("genre", "genres")):
            for name in snapshot[field]:
                name = name.strip()
                if name:
                    pairs[(kind, name_key(name))] = name
    UserCatalogTerm.objects.bulk_create(
        [
            UserCatalogTerm(user_id=entry.user_id, kind=kind, name_key=key, name=name)
            for (kind, key), name in pairs.items()
        ],
        ignore_conflicts=True,
    )
    terms = {
        (term.kind, term.name_key): term
        for term in UserCatalogTerm.objects.filter(
            user_id=entry.user_id, name_key__in=[key for _, key in pairs]
        )
    }
    UserCatalogLink.objects.filter(entry=entry).delete()
    UserCatalogLink.objects.bulk_create(
        [
            UserCatalogLink(
                entry=entry, term=terms[pair], version_id=entry.current_version_id
            )
            for pair in pairs
        ]
    )


def current_links(user_id):
    return Q(
        links__entry__user_id=user_id,
        links__entry_id__in=held_entries(user_id).values("pk"),
    ) & (
        Q(links__version_id=F("links__entry__current_version_id"))
        | Q(links__version__isnull=True, links__entry__current_version__isnull=True)
    )


def term_stats(user_id, kind, *, recent_days=180):
    if kind not in {"actor", "genre"}:
        raise ValueError("Invalid catalog kind")
    own = current_links(user_id)
    watched = Q(own_states__watched=True)
    favorite = Q(own_states__is_favorite=True)
    since = timezone.now() - timedelta(days=max(1, recent_days))
    return (
        UserCatalogTerm.objects.filter(user_id=user_id, user__is_active=True, kind=kind)
        .annotate(
            own_states=FilteredRelation(
                "links__entry__pool__resource__user_states",
                condition=Q(links__entry__pool__resource__user_states__user_id=user_id),
            )
        )
        .annotate(
            resource_count=Count("links__entry", filter=own, distinct=True),
            watched_count=Count("links__entry", filter=own & watched, distinct=True),
            favorite_count=Count("links__entry", filter=own & favorite, distinct=True),
            interacted_count=Count(
                "links__entry", filter=own & (watched | favorite), distinct=True
            ),
            recent_count=Count(
                "links__entry",
                filter=own & Q(links__entry__created_at__gte=since),
                distinct=True,
            ),
        )
        .filter(resource_count__gt=0)
    )


def own_term(user_id, kind, term_id):
    term = term_stats(user_id, kind).filter(pk=term_id).first()
    if term is None:
        raise LibraryNotFound("Catalog object not available")
    return term
