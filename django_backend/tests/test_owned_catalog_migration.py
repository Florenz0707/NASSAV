"""Owned taxonomy expansion preserves source versions and explicit legacy ownership."""

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone


@pytest.mark.django_db(transaction=True)
def test_catalog_upgrade_reverse_reupgrade_projects_only_proven_owner_without_global_copies():
    old = [("nassav", "0046_library_commands_and_quota")]
    new = [("nassav", "0047_owned_catalog_projection")]
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    try:
        executor.migrate(old)
        apps = executor.loader.project_state(old).apps
        User = apps.get_model("auth", "User")
        Resource = apps.get_model("nassav", "AVResource")
        Pool = apps.get_model("nassav", "ResourcePoolEntry")
        Entry = apps.get_model("nassav", "UserLibraryEntry")
        Version = apps.get_model("nassav", "ResourceVersion")
        users = [User.objects.create(username=f"catalog-{name}") for name in ("a", "b")]
        resource = Resource.objects.create(avid="CAT-047", source_title="legacy title")
        actor = apps.get_model("nassav", "Actor").objects.create(name="旧演员")
        genre = apps.get_model("nassav", "Genre").objects.create(name="旧类别")
        resource.actors.add(actor)
        resource.genres.add(genre)
        pool = Pool.objects.create(
            canonical_avid=resource.avid, resource=resource, state="ready"
        )
        version = Version.objects.create(
            pool=pool,
            pool_generation=1,
            kind="metadata",
            source_name="jable",
            owner=users[0],
            access_scope="personal:fixture-id",
            context_revision="fixture",
            state="ready",
            published_at=timezone.now(),
            metadata={
                "avid": "CAT-047",
                "actors": ["私人演员", " 私人演员 "],
                "genres": ["私人类别"],
            },
        )
        a = Entry.objects.create(
            user=users[0],
            pool=pool,
            state="active",
            current_version=version,
            access_scope=version.access_scope,
        )
        b = Entry.objects.create(
            user=users[1],
            pool=pool,
            state="active",
            access_scope=f"legacy:operator:{users[1].pk}",
        )
        for _ in range(2):
            executor = MigrationExecutor(connection)
            executor.migrate(new)
            state = executor.loader.project_state(new).apps
            Term, Link = (
                state.get_model("nassav", "UserCatalogTerm"),
                state.get_model("nassav", "UserCatalogLink"),
            )
            assert set(
                Term.objects.filter(user_id=users[0].pk).values_list("name", flat=True)
            ) == {"私人演员", "私人类别"}
            assert set(
                Term.objects.filter(user_id=users[1].pk).values_list("name", flat=True)
            ) == {"旧演员", "旧类别"}
            assert (
                Link.objects.filter(entry_id=a.pk, version_id=version.pk).count() == 2
            )
            assert (
                Link.objects.filter(entry_id=b.pk, version_id__isnull=True).count() == 2
            )
            assert state.get_model("nassav", "Actor").objects.count() == 1
            assert state.get_model("nassav", "Genre").objects.count() == 1
            assert (
                state.get_model("nassav", "ResourceVersion")
                .objects.get(pk=version.pk)
                .metadata
                == version.metadata
            )
            executor = MigrationExecutor(connection)
            executor.migrate(old)
            state = executor.loader.project_state(old).apps
            assert (
                state.get_model("nassav", "UserLibraryEntry")
                .objects.get(pk=a.pk)
                .current_version_id
                == version.pk
            )
            assert (
                state.get_model("nassav", "AVResource")
                .objects.get(pk=resource.pk)
                .source_title
                == "legacy title"
            )
            assert (
                state.get_model("nassav", "AVResource")
                .objects.get(pk=resource.pk)
                .actors.count()
                == 1
            )
    finally:
        MigrationExecutor(connection).migrate(latest)
