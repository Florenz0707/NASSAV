"""Production consumers resolve owned taxonomy, not a colliding global entity ID."""

from unittest.mock import Mock
import time

import pytest
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APIClient

from nassav import search_jobs
from nassav.catalog_projection import term_stats
from nassav.catalog_presentation import list_terms
from nassav.external_search import (
    ExternalSearchService,
    JableExternalSourceAdapter,
    MissAVExternalSourceAdapter,
)
from nassav.library_membership import LibraryNotFound
from nassav.library_catalog import list_entries
from nassav.models import Actor, ActorSourceMapping, Genre
from nassav.recommendation.seeds import LocalPreferenceSeedProvider
from nassav.recommendation.entities import RecommendationRequest
from nassav.recommendation.seed_profiles import recommendation_seed_profile_repository
from nassav.catalog_entities import CatalogEntity
from test_owned_catalog_projection import publish_terms
from test_version_publication import environment as environment, context
from test_external_search_detail_api import _FakeJableSource
from test_search_jobs import MemoryStore

pytestmark = pytest.mark.django_db


@pytest.fixture
def catalogs(environment, settings):
    users, vault, roots = environment
    settings.SHARED_LIBRARY_ENABLED = True
    settings.SOURCE_CREDENTIALS_ENABLED = False
    for user, name in zip(users, ("private A actor", "private B actor")):
        vault.write(
            user.pk,
            "jable",
            {
                "expected_version": 0,
                "cookie": f"account_session={user.pk}",
                "user_agent": "UA",
            },
        )
        publish_terms(
            user,
            context(vault, user),
            roots,
            actor=name,
            genre=f"private {user.pk} genre",
        )
    return users


def test_http_directory_and_exact_ids_never_return_another_owner(catalogs):
    users = catalogs
    first = term_stats(users[0].pk, "actor").get()
    client = APIClient()
    for user in users:
        client.force_login(user)
        with override_settings(NASSAV_OPERATOR_USERNAME=user.username):
            data = client.get("/nassav/api/actors").data
            assert data["pagination"]["total"] == 1
            assert (
                data["data"][0]["name"].casefold()
                == f"private {'a' if user == users[0] else 'b'} actor"
            )
            assert client.get("/nassav/api/genres").data["pagination"]["total"] == 1
            if user == users[1]:
                assert (
                    client.get(f"/nassav/api/actors?id={first.pk}").data["data"] == []
                )
                assert (
                    client.get(f"/nassav/api/actors/{first.pk}/detail").status_code
                    == 404
                )
                assert (
                    client.get(f"/nassav/api/actors/{first.pk}/avatar").status_code
                    == 404
                )
    assert not Actor.objects.exists() and not Genre.objects.exists()


def test_own_directory_ids_filter_version_library_and_foreign_ids_are_rejected(
    catalogs,
):
    users = catalogs
    actor = term_stats(users[0].pk, "actor").get()
    assert list_entries(users[0].pk, {"actor": str(actor.pk)})[1]["total"] == 1
    with pytest.raises(LibraryNotFound):
        list_entries(users[1].pk, {"actor": str(actor.pk)})


def test_recommendation_uses_own_current_terms_and_named_blacklist_only(catalogs):
    users = catalogs
    provider = LocalPreferenceSeedProvider()
    request = RecommendationRequest(user_id=users[0].pk)
    seeds = provider.get_seeds(request)
    assert {seed.seed_type for seed in seeds} == {"actor", "genre"}
    assert any(seed.value.casefold() == "private a actor" for seed in seeds)
    assert not any("private b" in seed.value.casefold() for seed in seeds)
    assert all(
        seed.lookup_payload["namespace"] == "owned-catalog-v1"
        and "actor_id" not in seed.lookup_payload
        for seed in seeds
    )
    term = term_stats(users[0].pk, "actor").get()
    recommendation_seed_profile_repository.for_user(users[0].pk).set_catalog_block(
        "actor", term.pk, blocked=True
    )
    assert not any(seed.seed_type == "actor" for seed in provider.get_seeds(request))
    assert any(
        seed.seed_type == "actor"
        for seed in provider.get_seeds(RecommendationRequest(user_id=users[1].pk))
    )


def test_seed_block_http_checks_own_term_and_does_not_use_global_pk_collision(catalogs):
    users = catalogs
    term = term_stats(users[0].pk, "actor").get()
    # This ID is deliberately a different global actor; it must never be blocked.
    Actor.objects.create(pk=term.pk, name="unrelated global actor")
    client = APIClient()
    client.force_login(users[0])
    with override_settings(NASSAV_OPERATOR_USERNAME=users[0].username):
        response = client.post(
            "/nassav/api/recommendations/seed-block",
            {"seed_type": "actor", "id": term.pk},
            format="json",
        )
        assert (
            response.status_code == 200 and response.data["data"]["name"] == term.name
        )
    assert not recommendation_seed_profile_repository.for_user(
        users[0].pk
    ).get_blocked_normalized_values(
        seed_type="actor", values=["unrelated global actor"]
    )
    client.force_login(users[1])
    with override_settings(NASSAV_OPERATOR_USERNAME=users[1].username):
        assert (
            client.post(
                "/nassav/api/recommendations/seed-block",
                {"seed_type": "actor", "id": term.pk},
                format="json",
            ).status_code
            == 404
        )


def test_external_search_uses_owned_name_and_separate_cache_identity(
    catalogs, settings, monkeypatch
):
    users = catalogs
    cache.clear()
    cache_set = Mock(wraps=cache.set)
    monkeypatch.setattr(cache, "set", cache_set)
    settings.EXTERNAL_SEARCH_FETCH_PAGES = 1
    settings.EXTERNAL_SEARCH_CACHE_ENABLED = True
    term = term_stats(users[0].pk, "actor").get()
    global_actor = Actor.objects.create(pk=term.pk, name="wrong actor")
    ActorSourceMapping.objects.create(
        actor=global_actor, source_name="jable", source_actor_slug="wrong-slug"
    )
    fake = _FakeJableSource()
    fake.domain = "jable.tv"
    fake.proxy = None
    service = ExternalSearchService(
        adapters={"jable": JableExternalSourceAdapter(source_lookup=lambda name: fake)}
    )
    result = service.search_actor_detail(
        actor_id=term.pk,
        source_name="jable",
        page=1,
        page_size=20,
        ordering="-views",
        user_id=users[0].pk,
    )
    assert result.meta["actor"]["name"] == term.name
    assert fake.search_calls[0][0] == term.name and not fake.model_calls
    with pytest.raises(LibraryNotFound):
        service.search_actor_detail(
            actor_id=term.pk,
            source_name="jable",
            page=1,
            page_size=20,
            ordering="-views",
            user_id=users[1].pk,
        )
    assert any(
        "owned-catalog-v1" in str(call.args[0]) for call in cache_set.call_args_list
    )


def test_missav_adapter_does_not_lookup_global_mapping_for_owned_entity(monkeypatch):
    from nassav.external_search import actor_source_mapping_service

    lookup = Mock(
        side_effect=AssertionError("Global mapping must not receive owned IDs")
    )
    monkeypatch.setattr(
        actor_source_mapping_service, "get_actor_source_mappings", lookup
    )
    adapter = MissAVExternalSourceAdapter(source_lookup=lambda name: None)
    adapter._search = Mock(return_value=[])
    entity = CatalogEntity(1, "private actor", 1, "owned-catalog-v1:hash")
    assert adapter.search_actor_items(actor=entity, page=1, ordering="-views") == []
    assert adapter._search.call_args.args[:2] == ("search", "private actor")


def test_old_search_namespace_is_rejected_and_cancelled_before_fetch(
    catalogs, monkeypatch
):
    users = catalogs
    store = MemoryStore()
    monkeypatch.setattr(search_jobs, "_publish", Mock())
    monkeypatch.setattr(search_jobs.run_search_job.app.control, "revoke", Mock())
    snapshot = {
        "task_id": "old-search",
        "state": "queued",
        "submitted_at": time.time(),
        "query_key": "old-key",
        "owner_id": users[0].pk,
        "owner_epoch": 1,
        "query": {
            "entity_type": "actor",
            "entity_id": 1,
            "source": "jable",
            "page": 1,
            "page_size": 20,
            "ordering": "-views",
            "force_refresh": False,
        },
        "result": None,
    }
    store.rows["old-search"] = snapshot
    store.locks["old-key"] = "old-search"
    with pytest.raises(search_jobs.SearchJobAccessExpired):
        search_jobs.get_search_job("old-search", store=store)
    result = search_jobs.execute_search_job("old-search", store=store)
    assert result["state"] == "cancelled"
    assert not store.locks


def test_completed_search_handle_rechecks_account_epoch_without_mutating_snapshot(
    catalogs,
):
    users = catalogs
    store = MemoryStore()
    from nassav.account_models import UserAccount

    snapshot = {
        "task_id": "finished",
        "state": "succeeded",
        "owner_id": users[0].pk,
        "owner_epoch": 1,
        "query": {"catalog_namespace": "owned-catalog-v1"},
        "result": None,
        "version": 4,
    }
    store.rows["finished"] = snapshot
    assert search_jobs.get_search_job("finished", store=store)["version"] == 4
    UserAccount.objects.filter(user=users[0]).update(version=2)
    with pytest.raises(search_jobs.SearchJobAccessExpired):
        search_jobs.get_search_job("finished", store=store)
    assert store.rows["finished"] == snapshot


def test_owned_search_submit_resolves_term_and_worker_calls_owned_name(
    catalogs, monkeypatch, settings
):
    users = catalogs
    settings.EXTERNAL_SEARCH_FETCH_PAGES = 1
    settings.EXTERNAL_SEARCH_CACHE_ENABLED = False
    fake = _FakeJableSource()
    fake.domain = "jable.tv"
    fake.proxy = None
    service = ExternalSearchService(
        adapters={"jable": JableExternalSourceAdapter(source_lookup=lambda name: fake)}
    )
    monkeypatch.setattr(search_jobs, "external_search_service", service)
    monkeypatch.setattr(search_jobs, "_publish", Mock())
    monkeypatch.setattr(search_jobs.run_search_job, "apply_async", Mock())
    store = MemoryStore()
    term = term_stats(users[0].pk, "actor").get()
    body = {
        "entity_type": "actor",
        "entity_id": term.pk,
        "source": "jable",
        "ordering": "-views",
    }
    job, _ = search_jobs.submit_search_job(body, store=store, user_id=users[0].pk)
    assert job["query"]["catalog_namespace"] == "owned-catalog-v1"
    result = search_jobs.execute_search_job(job["task_id"], store=store)
    assert (
        result["state"] == "succeeded"
        and result["result"]["data"]["detail"]["name"] == term.name
    )
    assert fake.search_calls[0][0] == term.name
    with pytest.raises(LibraryNotFound):
        search_jobs.submit_search_job(body, store=store, user_id=users[1].pk)


def test_directory_paging_and_seed_scores_are_batched_and_owner_bound(
    catalogs, django_assert_num_queries
):
    users = catalogs
    with django_assert_num_queries(4, exact=False):
        data, pagination = list_terms(users[0].pk, "genre", {})
    assert pagination["total"] == 1 and data[0]["source_mapping"] is None
    with pytest.raises(ValueError):
        list_terms(users[0].pk, "actor", {"page_size": 101})
    with pytest.raises(ValueError):
        list_terms(users[0].pk, "actor", {"order_by": "ciphertext"})


@pytest.mark.django_db(transaction=True)
def test_legacy_avatar_is_owned_and_refuses_path_escape(
    environment, settings, tmp_path
):
    from nassav.models import AVResource
    from nassav.library_import import import_legacy_library

    users, _, _ = environment
    settings.SHARED_LIBRARY_ENABLED = True
    settings.AVATAR_DIR = tmp_path / "avatars"
    settings.AVATAR_DIR.mkdir()
    resource = AVResource.objects.create(avid="LEG-AVATAR")
    actor = Actor.objects.create(name="Legacy actor", avatar_filename="legacy.jpg")
    resource.actors.add(actor)
    settings.AVATAR_DIR.joinpath("legacy.jpg").write_bytes(b"legacy image fixture")
    import_legacy_library(users[0].username, apply=True)
    term = term_stats(users[0].pk, "actor").get()
    client = APIClient()
    client.force_login(users[0])
    with override_settings(NASSAV_OPERATOR_USERNAME=users[0].username):
        response = client.get(f"/nassav/api/actors/{term.pk}/avatar")
        assert (
            response.status_code == 200
            and response["Cache-Control"] == "private, no-store"
        )
        assert b"".join(response.streaming_content) == b"legacy image fixture"
        response.close()
        Actor.objects.filter(pk=actor.pk).update(avatar_filename="../outside.jpg")
        assert client.get(f"/nassav/api/actors/{term.pk}/avatar").status_code == 404
    client.force_login(users[1])
    with override_settings(NASSAV_OPERATOR_USERNAME=users[1].username):
        assert client.get(f"/nassav/api/actors/{term.pk}/avatar").status_code == 404


def test_current_avatar_address_uses_authorized_version_and_not_global_actor_id(
    catalogs, settings
):
    from nassav.resource_version_models import ResourceVersion
    import hashlib

    users = catalogs
    version = ResourceVersion.objects.get(owner=users[0])
    source_name = version.metadata["actors"][0]
    asset = {
        "root": "avatar",
        "kind": "avatar",
        "path": f"versions/{version.pk}/avatars/{hashlib.sha256(source_name.encode()).hexdigest()}.jpg",
        "size": 100,
        "sha256": "a" * 64,
        "marker": "fixture-not-serving-bytes",
    }
    ResourceVersion.objects.filter(pk=version.pk).update(
        manifest=[*version.manifest, asset]
    )
    data, _ = list_terms(users[0].pk, "actor", {})
    assert "/api/library/entries/" in data[0]["avatar_url"]
    assert "/images/" in data[0]["avatar_url"]
    assert str(version.pk) not in data[0]["avatar_url"]
