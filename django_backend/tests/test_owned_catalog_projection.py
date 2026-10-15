"""Owned current-version taxonomy never aggregates another user's source or states."""

import pytest
from django.db import transaction

from nassav.catalog_models import UserCatalogTerm, UserCatalogLink
from nassav.catalog_projection import term_stats, own_term, sync_entry, name_key
from nassav.library_models import UserLibraryEntry
from nassav.library_membership import LibraryNotFound
from nassav.personal_state import update_state, lock_user
from nassav.models import Actor, Genre
from nassav.resource_version_models import ResourceVersion
from nassav.task_assets import AssetPromotion
from nassav import composition
from test_version_publication import (
    environment as environment,
    context,
    runtime,
    operation,
    claim,
    staged_cover,
)

pytestmark = pytest.mark.django_db


def publish_terms(user, ctx, roots, *, actor, genre, action="add"):
    tasks, pub, operations, assets = runtime(ctx, roots)
    op = operation(user, ctx, operations, action=action)
    token = claim(tasks, op)
    version = pub.prepare(token)
    artifact = staged_cover(assets, token)
    row = assets.commit(
        token,
        [AssetPromotion(artifact, pub.target(version, "cover.jpg"))],
        lambda: pub.publish(
            token,
            version,
            {
                "avid": "PUB-001",
                "actors": [actor, actor.upper()],
                "genres": [genre],
                "source_title": "own metadata",
            },
        ),
        resource_saved=True,
    )
    tasks.finish(token, "succeeded")
    operations.project(user.pk, op["operation_id"])
    return row, UserLibraryEntry.objects.select_related(
        "pool__resource", "current_version"
    ).get(user=user)


def test_private_terms_never_enter_global_models_and_stats_are_current_owned(
    environment, settings
):
    users, vault, roots = environment
    settings.SHARED_LIBRARY_ENABLED = True
    entries = []
    for user, actor in zip(users, ("private A actor", "private B actor")):
        vault.write(
            user.pk,
            "jable",
            {
                "expected_version": 0,
                "cookie": f"account_session={user.pk}",
                "user_agent": "UA",
            },
        )
        _, entry = publish_terms(
            user,
            context(vault, user),
            roots,
            actor=actor,
            genre=f"private genre {user.pk}",
        )
        entries.append(entry)
    assert not Actor.objects.exists() and not Genre.objects.exists()
    assert UserCatalogTerm.objects.count() == 4 and UserCatalogLink.objects.count() == 4
    update_state(entries[0].pool.resource, users[0].pk, {"is_favorite": True})
    update_state(entries[1].pool.resource, users[1].pk, {"watched": True})
    first = term_stats(users[0].pk, "actor").get()
    second = term_stats(users[1].pk, "actor").get()
    assert first.name.casefold() == "private a actor"
    assert (
        first.resource_count == 1
        and first.favorite_count == 1
        and first.watched_count == 0
    )
    assert (
        second.resource_count == 1
        and second.watched_count == 1
        and second.favorite_count == 0
    )
    with pytest.raises(LibraryNotFound):
        own_term(users[1].pk, "actor", first.pk)
    composition.build_library_membership().release(
        users[0].pk, entries[0].pk, expected_version=entries[0].version
    )
    assert not term_stats(users[0].pk, "actor").exists()
    assert not UserCatalogLink.objects.filter(entry_id=entries[0].pk).exists()
    assert term_stats(users[1].pk, "actor").get().resource_count == 1


def test_metadata_switch_replaces_links_but_other_holder_keeps_own_old_projection(
    environment, settings
):
    users, vault, roots = environment
    settings.SHARED_LIBRARY_ENABLED = True
    ctx = context(vault)
    first, entry = publish_terms(
        users[0], ctx, roots, actor="old actor", genre="old genre"
    )
    # The second holder reuses this exact ready metadata under its own user fence.
    _, _, operations, _ = runtime(ctx, roots)
    operation(users[1], ctx, operations)
    assert term_stats(users[1].pk, "actor").get().resource_count == 1
    newer, entry = publish_terms(
        users[0], ctx, roots, actor="new actor", genre="new genre", action="refresh"
    )
    assert first.pk != newer.pk
    assert term_stats(users[0].pk, "actor").get().name.casefold() == "new actor"
    assert term_stats(users[1].pk, "actor").get().name.casefold() == "old actor"
    assert not UserCatalogLink.objects.filter(entry=entry, version=first).exists()
    assert UserCatalogLink.objects.filter(entry=entry, version=newer).count() == 2
    old = UserCatalogTerm.objects.get(user=users[0], name_key=name_key("old actor"))
    with pytest.raises(LibraryNotFound):
        own_term(users[0].pk, "actor", old.pk)


def test_stale_cross_owner_and_wrong_version_links_cannot_restore_counts(
    environment, settings
):
    users, vault, roots = environment
    settings.SHARED_LIBRARY_ENABLED = True
    version, entry = publish_terms(
        users[0], context(vault), roots, actor="known actor", genre="known genre"
    )
    other_term = UserCatalogTerm.objects.create(
        user=users[1],
        kind="actor",
        name="foreign secret",
        name_key=name_key("foreign secret"),
    )
    UserCatalogLink.objects.create(entry=entry, term=other_term, version=version)
    assert not term_stats(users[1].pk, "actor").exists()
    newer = ResourceVersion.objects.create(
        pool=entry.pool,
        pool_generation=1,
        kind="metadata",
        source_name="jable",
        access_scope="public",
        context_revision="new",
        state="ready",
        published_at=version.published_at,
        metadata={"avid": "PUB-001"},
    )
    UserLibraryEntry.objects.filter(pk=entry.pk).update(current_version=newer)
    assert not term_stats(users[0].pk, "actor").exists()
    entry.refresh_from_db()
    with transaction.atomic():
        lock_user(users[0].pk)
        sync_entry(entry)
    assert not UserCatalogLink.objects.filter(entry=entry).exists()


def test_owned_statistics_use_one_query_without_per_term_state_reads(
    environment, settings, django_assert_num_queries
):
    users, vault, roots = environment
    settings.SHARED_LIBRARY_ENABLED = True
    _, entry = publish_terms(
        users[0], context(vault), roots, actor="Actor", genre="Genre"
    )
    with django_assert_num_queries(1):
        rows = list(term_stats(users[0].pk, "actor"))
    assert rows[0].resource_count == 1 and rows[0].watched_count == 0
