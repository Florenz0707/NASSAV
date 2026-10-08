"""R2 search extension: uv run pytest tests/test_search_adapter_contracts.py -v."""

from unittest.mock import Mock

import pytest
from nassav.external_search import (
    ExternalSearchService,
    ExternalSourceAdapter,
    JableExternalSourceAdapter,
    SearchCapability,
)
from nassav.source.capabilities import ListingSource


class TestListingAdapter(ExternalSourceAdapter):
    __test__ = False
    source_name = "test-listing"
    implemented = True

    def __init__(self, *, native_order=False, domain="test.invalid"):
        self.native_order = native_order
        self.domain = domain
        self.calls = []

    def capability(self):
        return SearchCapability(
            self.source_name, "Test listing", native_order=self.native_order
        )

    def is_enabled(self):
        return True

    def cache_context(self):
        return self.domain, "direct"

    def search_actor_items(self, *, actor, page, ordering, force_refresh=False):
        self.calls.append(page)
        if page > 1:
            return []
        return [
            {"avid": "LOW-001", "metrics": {"views": 1}},
            {"avid": "HIGH-001", "metrics": {"views": 9}},
        ]

    def search_genre_items(self, *, genre, page, ordering, force_refresh=False):
        return self.search_actor_items(
            actor=genre, page=page, ordering=ordering, force_refresh=force_refresh
        )


@pytest.mark.django_db
@pytest.mark.parametrize("native_order", [False, True])
def test_new_listing_adapter_requires_no_generic_source_branch(
    actor_factory, settings, native_order
):
    settings.EXTERNAL_SEARCH_CACHE_ENABLED = False
    settings.EXTERNAL_SEARCH_FETCH_PAGES = 2
    actor = actor_factory()
    adapter = TestListingAdapter(native_order=native_order)
    service = ExternalSearchService(adapters={adapter.source_name: adapter})
    assert service.capabilities()[0]["label"] == "Test listing"
    result = service.search_actor_detail(
        actor_id=actor.pk,
        source_name=adapter.source_name,
        page=1,
        page_size=20,
        ordering="-views",
    )
    expected = ["LOW-001", "HIGH-001"] if native_order else ["HIGH-001", "LOW-001"]
    assert [item["avid"] for item in result.items] == expected
    assert result.meta["source"] == adapter.source_name
    assert adapter.calls == [1, 2]


class BrokenListing(ListingSource):
    def __init__(self):
        self.calls = 0

    def search_listing(
        self, kind, term, *, page=1, ordering="-views", force_refresh=False
    ):
        self.calls += 1
        raise TypeError("bug inside listing implementation")


def test_type_error_in_listing_implementation_is_not_retried():
    source = BrokenListing()
    adapter = JableExternalSourceAdapter(source_lookup=lambda name: source)
    actor = Mock(pk=1, name="Actor")
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(
            "nassav.external_search.actor_source_mapping_service.get_actor_source_mappings",
            lambda **kwargs: {},
        )
        with pytest.raises(TypeError, match="bug inside"):
            adapter.search_actor_items(actor=actor, page=1, ordering="-views")
    assert source.calls == 1


@pytest.mark.django_db
def test_adapter_cache_context_separates_domains(actor_factory, settings):
    from django.core.cache import cache

    cache.clear()
    settings.EXTERNAL_SEARCH_CACHE_ENABLED = True
    settings.EXTERNAL_SEARCH_FETCH_PAGES = 1
    actor = actor_factory()
    adapters = [
        TestListingAdapter(domain="first.invalid"),
        TestListingAdapter(domain="second.invalid"),
    ]
    for adapter in adapters:
        service = ExternalSearchService(adapters={adapter.source_name: adapter})
        for _ in range(2):
            service.search_actor_detail(
                actor_id=actor.pk,
                source_name=adapter.source_name,
                page=1,
                page_size=20,
                ordering="-views",
            )
        assert adapter.calls == [1]


@pytest.mark.django_db
def test_aggregate_cache_reuses_raw_results_and_reprojects_library(
    actor_factory, resource_factory, settings
):
    from django.core.cache import cache

    settings.EXTERNAL_SEARCH_CACHE_ENABLED = True
    settings.EXTERNAL_SEARCH_FETCH_PAGES = 2
    cache.clear()
    actor = actor_factory()
    adapter = TestListingAdapter()
    service = ExternalSearchService(adapters={adapter.source_name: adapter})
    query = dict(
        actor_id=actor.pk,
        source_name=adapter.source_name,
        page=1,
        page_size=20,
        ordering="-views",
    )
    first = service.search_actor_detail(**query)
    assert not first.meta["cache"]["hit"]
    saved = resource_factory(avid="LOW-001")
    second = service.search_actor_detail(**query)
    assert second.meta["cache"]["hit"] and adapter.calls == [1, 2]
    assert next(item for item in second.items if item["avid"] == "LOW-001")[
        "in_library"
    ]
    assert not next(item for item in first.items if item["avid"] == "LOW-001")[
        "in_library"
    ]
    saved.delete()
    third = service.search_actor_detail(**{**query, "page": 2, "page_size": 1})
    assert third.meta["cache"]["hit"] and not third.items[0]["in_library"]
    service.search_actor_detail(**query, force_refresh=True)
    assert adapter.calls == [1, 2, 1, 2]
    cache.clear()


@pytest.mark.django_db
def test_async_cache_is_deferred_until_authoritative_success(actor_factory, settings):
    from django.core.cache import cache

    settings.EXTERNAL_SEARCH_CACHE_ENABLED = True
    settings.EXTERNAL_SEARCH_FETCH_PAGES = 1
    cache.clear()
    actor = actor_factory()
    adapter = TestListingAdapter()
    service = ExternalSearchService(adapters={adapter.source_name: adapter})
    query = dict(
        actor_id=actor.pk,
        source_name=adapter.source_name,
        page=1,
        page_size=20,
        ordering="-views",
    )
    pending = service.search_actor_detail(**query, defer_cache_publication=True)
    assert pending.publish_cache is not None
    another = service.search_actor_detail(**query, defer_cache_publication=True)
    assert not another.meta["cache"]["hit"]
    pending.publish_cache()
    hit = service.search_actor_detail(**query)
    assert hit.meta["cache"]["hit"]
    key = f"external-search:v5:cn:actor:{actor.pk}:test-listing:test.invalid:direct:1:-views"
    assert all(
        "in_library" not in item and "detail_cached" not in item
        for item in cache.get(key)
    )
    cache.clear()
