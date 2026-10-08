from datetime import timedelta
from dataclasses import replace
from uuid import uuid4
from unittest.mock import Mock

import pytest
from django.utils import timezone
from nassav.models import AVResource, ResourceMetadataCache, ResourcePlaybackCache
from nassav.resource_cache import (
    CacheKey,
    CachePolicy,
    CachePublicationLost,
    DjangoProviderFactsStore,
    ProviderFactsCache,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def setup_cache():
    time = [timezone.now()]
    store = DjangoProviderFactsStore()
    service = ProviderFactsCache(store, now=lambda: time[0])
    key = CacheKey.create(
        "test-001", "source", "Jable", scope="jable.tv", variant="/videos/test-001/"
    )
    policy = CachePolicy("detail-v3", frozenset({"actors"}), timedelta(days=7))
    return service, store, key, policy, time


def test_persistent_facts_survive_library_deletion_and_preserve_empty_fields(
    setup_cache,
):
    cache, _, key, policy, _ = setup_cache
    payload = {"actors": [], "title": "title"}
    fetch = Mock(return_value=payload)
    assert not cache.resolve(key, policy, fetch).hit
    payload["title"] = "mutated"
    AVResource.objects.create(avid=key.avid).delete()
    assert cache.resolve(key, policy, fetch).payload["title"] == "title"
    assert cache.resolve(key, policy, fetch).hit
    assert fetch.call_count == 1
    assert AVResource.objects.count() == 0


def test_expiry_parser_and_completeness_force_new_lookup(setup_cache):
    cache, _, key, policy, time = setup_cache
    cache.resolve(key, policy, lambda: {"actors": []})
    assert not cache.read_many([key], replace(policy, parser_version="new"))
    assert not cache.read_many(
        [key], replace(policy, required_fields=frozenset({"genres"}))
    )
    time[0] += timedelta(days=8)
    assert not cache.read_many([key], policy)
    assert not cache.resolve(key, policy, lambda: {"actors": ["new"]}).hit
    assert not cache.resolve(key, policy, lambda: {"actors": []}, force=True).hit


def test_sources_scopes_variants_and_playback_are_independent(setup_cache):
    cache, _, key, policy, _ = setup_cache
    cache.resolve(key, policy, lambda: {"actors": []})
    other = CacheKey.create(
        key.avid, "source", "Jable", scope="other", variant="/videos/test-001/"
    )
    assert not cache.read_many([other], policy)
    assert not cache.read_many([key], policy, playback=True)
    cache.resolve(key, policy, lambda: {"actors": ["playback"]}, playback=True)
    assert (
        ResourceMetadataCache.objects.count()
        == ResourcePlaybackCache.objects.count()
        == 1
    )


def test_failure_empty_and_cancelled_fetch_do_not_replace_good_payload(setup_cache):
    cache, _, key, policy, _ = setup_cache
    cache.resolve(key, policy, lambda: {"actors": ["good"]})
    assert not cache.resolve(key, policy, lambda: {}, force=True).payload
    with pytest.raises(ValueError):
        cache.resolve(key, policy, lambda: {"wrong": True}, force=True)
    stopped = [False]

    def check():
        if stopped[0]:
            raise RuntimeError("cancelled")

    def fetch():
        stopped[0] = True
        return {"actors": ["late"]}

    with pytest.raises(RuntimeError, match="cancelled"):
        cache.resolve(key, policy, fetch, force=True, check=check)
    assert cache.resolve(key, policy, Mock()).payload == {"actors": ["good"]}
    assert ResourceMetadataCache.objects.get().fetch_owner is None


def test_owner_expiry_invalidation_and_purge_reject_old_publish(setup_cache):
    cache, store, key, policy, time = setup_cache
    now = time[0]
    first = store.claim(key, uuid4(), now, now + timedelta(seconds=1))
    assert store.claim(key, uuid4(), now, now + timedelta(seconds=10)) is None
    time[0] += timedelta(seconds=2)
    second = store.claim(key, uuid4(), time[0], time[0] + timedelta(seconds=10))
    assert not store.publish(first, {"actors": ["old"]}, policy, time[0])
    store.release(first)
    assert ResourceMetadataCache.objects.get().fetch_owner == second.owner
    store.invalidate(key)
    assert not store.publish(second, {"actors": []}, policy, time[0])

    def purged():
        ResourceMetadataCache.objects.all().delete()
        return {"actors": []}

    with pytest.raises(CachePublicationLost):
        cache.resolve(key, policy, purged)
    assert ResourceMetadataCache.objects.count() == 0


def test_waiting_checks_cancellation_without_fetching(setup_cache):
    cache, store, key, policy, time = setup_cache
    store.claim(key, uuid4(), time[0], time[0] + timedelta(seconds=30))
    stopped = [False]
    cache.wait = lambda _: stopped.__setitem__(0, True)

    def check():
        if stopped[0]:
            raise RuntimeError("stop")

    fetch = Mock()
    with pytest.raises(RuntimeError, match="stop"):
        cache.resolve(key, policy, fetch, check=check)
    fetch.assert_not_called()


def test_publication_fence_rejects_after_fetch(setup_cache):
    cache, _, key, policy, _ = setup_cache

    def fence(callback):
        raise RuntimeError("old task")

    with pytest.raises(RuntimeError, match="old task"):
        cache.resolve(key, policy, lambda: {"actors": []}, fence=fence)
    assert not cache.read_many([key], policy)
