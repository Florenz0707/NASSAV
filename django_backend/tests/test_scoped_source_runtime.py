"""Real scoped records with synthetic provider responses, no external credentials."""

from datetime import timedelta
from dataclasses import replace
from unittest.mock import Mock
from importlib import import_module

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.cache import cache

from nassav.credential_crypto import CredentialKeyring, CredentialUnavailable
from nassav.credential_records import DjangoCredentialRecords
from nassav.credential_models import SourceSessionSnapshot
from nassav.page_fetching.contracts import BrowserPageClient, PageResult
from nassav.page_fetching.proxy_server import ProxySessionCapabilities
from nassav.page_fetching.service import PageFetchService
from nassav.provider_facts import source_key, playback_key, SourceFactsLookup
from nassav.scoped_source_context import CredentialSourceContext
from nassav.source.Jable import Jable
from nassav.models import SourceCookie, ResourceMetadataCache, ResourcePlaybackCache
from nassav.composition import build_provider_facts_cache

pytestmark = pytest.mark.django_db

DETAIL = '<title>ABC-001 Private - Jable.TV</title><script>var hlsUrl = "https://media.test/master.m3u8";</script><section class="video-info"></section>'
CAPABILITIES = ProxySessionCapabilities(
    isolated_contexts=True, challenge_replay=True, context_revision="fixture-v1"
)


@pytest.fixture
def runtime():
    users = [
        get_user_model().objects.create_user(username=name)
        for name in ("scoped-a", "scoped-b")
    ]
    records = DjangoCredentialRecords(
        CredentialKeyring("k1", {"k1": b"a" * 32}), {"jable": "jable.tv"}
    )
    for index, user in enumerate(users):
        records.write(
            user.pk,
            "jable",
            {
                "expected_version": 0,
                "cookie": f"account_session=user-{index}; cf_clearance=old",
                "user_agent": "fixture-UA",
            },
        )
    return users, records


def context(records, user_id, *, capabilities=CAPABILITIES):
    return CredentialSourceContext(
        lambda: records,
        "jable",
        user_id=user_id,
        egress_profile="direct",
        browser_context="fixture-v1",
        capabilities=capabilities,
    )


def browser_result():
    return PageResult(
        html="Anonymous content",
        final_url="https://jable.tv/videos/abc-001/",
        provider="fixture",
        user_agent="fixture-UA",
        cookies=(
            {
                "name": "cf_clearance",
                "value": "new",
                "domain": "jable.tv",
                "path": "/",
                "expires": (timezone.now() + timedelta(minutes=5)).timestamp(),
            },
            {
                "name": "account_session",
                "value": "anonymous",
                "domain": "jable.tv",
                "path": "/",
            },
        ),
    )


def private_result():
    return PageResult(
        html=DETAIL,
        final_url="https://jable.tv/videos/abc-001/",
        provider="direct",
        target_status=200,
    )


def test_private_browser_result_requires_bound_replay_and_preserves_account(runtime):
    (first, _), records = runtime
    scope = context(records, first.pk)
    direct = Mock(return_value=private_result())
    result = scope.bind_browser_page(
        browser_result().final_url,
        browser_result(),
        lambda html: "Private" in html,
        direct,
    )
    assert result.html == DETAIL
    assert (
        direct.call_args.kwargs["session_override"].cookie
        == "account_session=user-0; cf_clearance=new"
    )
    assert direct.call_args.kwargs["session_override"].user_agent == "fixture-UA"
    assert SourceSessionSnapshot.objects.get().ciphertext
    assert not SourceCookie.objects.exists()
    assert scope.load_session().cookie == "account_session=user-0; cf_clearance=new"


@pytest.mark.parametrize(
    "change",
    [{"user_agent": "other-UA"}, {"final_url": "https://other.test/"}, {"cookies": ()}],
)
def test_invalid_browser_identity_never_returns_anonymous_private_success(
    runtime, change
):
    (first, _), records = runtime
    direct = Mock(return_value=private_result())
    result = context(records, first.pk).bind_browser_page(
        browser_result().final_url,
        replace(browser_result(), **change),
        lambda _: True,
        direct,
    )
    assert not result.ok and not result.html
    assert not direct.called and not SourceSessionSnapshot.objects.exists()


def test_failed_replay_and_unsupported_capability_do_not_publish(runtime):
    (first, _), records = runtime
    result = browser_result()
    for capabilities, probe in (
        (CAPABILITIES, replace(private_result(), target_status=403, html="denied")),
        (ProxySessionCapabilities(), private_result()),
    ):
        response = context(
            records, first.pk, capabilities=capabilities
        ).bind_browser_page(
            result.final_url,
            result,
            lambda html: "Private" in html,
            Mock(return_value=probe),
        )
        assert not response.ok
    assert not SourceSessionSnapshot.objects.exclude(ciphertext="").exists()
    assert not SourceSessionSnapshot.objects.exclude(refresh_owner=None).exists()


def test_revoke_during_probe_cannot_publish(runtime):
    (first, _), records = runtime
    scope = context(records, first.pk)

    def direct(*args, **kwargs):
        records.write(first.pk, "jable", {"expected_version": 1}, revoke=True)
        return private_result()

    with pytest.raises(CredentialUnavailable):
        scope.bind_browser_page(
            browser_result().final_url, browser_result(), lambda _: True, direct
        )
    assert not SourceSessionSnapshot.objects.exclude(ciphertext="").exists()


def test_cookie_origin_redirect_and_cdn_protection(runtime, monkeypatch):
    (first, _), records = runtime
    source = Jable()
    source.bind_credential_context(context(records, first.pk))
    source.load_cookie_from_db()
    response = Mock(
        status_code=200, url="https://jable.tv/videos/abc-001/", text=DETAIL
    )
    transport = Mock(return_value=response)
    monkeypatch.setattr(
        import_module("nassav.source.SourceBase").requests, "get", transport
    )
    assert source.fetch_page(response.url).ok
    assert transport.call_args.kwargs["headers"]["Cookie"].startswith(
        "account_session=user-0"
    )
    assert transport.call_args.kwargs["allow_redirects"] is False
    source._fetch("https://media.test/asset", headers={"Cookie": source.cookie})
    assert "Cookie" not in transport.call_args.kwargs["headers"]
    response.status_code = 302
    assert not source.fetch_page(response.url).ok


def test_page_service_cannot_disable_private_binding_with_reuse_flag(runtime):
    (first, _), records = runtime

    class Browser(BrowserPageClient):
        def fetch(self, url, *, timeout_ms):
            return browser_result()

    fetcher = PageFetchService(Browser(), session_reuse_enabled=False)
    source = Jable(page_fetcher=fetcher)
    source.bind_credential_context(context(records, first.pk))
    source.fetch_page = Mock(return_value=private_result())
    assert source.get_html("ABC-001") == DETAIL
    assert source.fetch_page.call_count == 1


def test_cache_keys_and_revocation_isolate_provider_and_listing_results(runtime):
    (first, second), records = runtime
    sources = [Jable(facts_cache=build_provider_facts_cache()) for _ in range(2)]
    for source, user in zip(sources, (first, second), strict=True):
        source.bind_credential_context(context(records, user.pk))
        source.get_html = Mock(return_value=DETAIL)
    assert source_key(sources[0], "ABC-001") != source_key(sources[1], "ABC-001")
    assert playback_key(sources[0], "ABC-001") != playback_key(sources[1], "ABC-001")
    assert sources[0]._build_cache_key("search", keyword="abc") != sources[
        1
    ]._build_cache_key("search", keyword="abc")
    SourceFactsLookup(sources[0].facts_cache, sources[0]).resolve(
        "ABC-001", require_playback=True
    )
    assert (
        ResourceMetadataCache.objects.count()
        == ResourcePlaybackCache.objects.count()
        == 1
    )
    assert not SourceFactsLookup(sources[1].facts_cache, sources[1]).read_details(
        [("ABC-001", "")]
    )
    records.write(first.pk, "jable", {"expected_version": 1}, revoke=True)
    with pytest.raises(CredentialUnavailable):
        SourceFactsLookup(sources[0].facts_cache, sources[0]).read_details(
            [("ABC-001", "")]
        )
    cache.clear()


def test_production_factories_external_scopes_and_missing_keys_fail_closed(
    runtime, settings, monkeypatch
):
    from nassav import composition
    from nassav.page_fetching.proxy_server import OrderedProxyServer
    from nassav.external_search import ExternalSearchService

    (first, second), records = runtime
    settings.SOURCE_CREDENTIALS_ENABLED = True
    monkeypatch.setattr(composition, "build_credential_records", lambda: records)
    server = OrderedProxyServer(session_capabilities=CAPABILITIES)
    save_old_cookie = Mock()
    for user, expected in ((first, "user-0"), (second, "user-1")):
        factories = composition.source_factories(
            None,
            settings.BROWSER_FETCH_CONFIG,
            save_old_cookie,
            proxy_server=server,
            user_id=user.pk,
        )
        source = factories["jable"]()
        assert source.load_cookie_from_db()
        assert expected in source.cookie
        assert not source.set_cookie_auto(force_refresh=True)
    assert not save_old_cookie.called
    service = ExternalSearchService(proxy_server=server)
    a, b = service.for_user(first.pk), service.for_user(second.pk)
    assert a.cache_context("jable") != b.cache_context("jable")
    with a.adapters["jable"].operation(lambda: None) as adapter:
        assert adapter.source_lookup("jable").cookie.startswith(
            "account_session=user-0"
        )
    records.write(
        first.pk,
        "jable",
        {
            "expected_version": 1,
            "cookie": "account_session=manual",
            "user_agent": "fixture-UA",
        },
    )
    with pytest.raises(CredentialUnavailable):
        a.cache_context("jable")
    assert b.cache_context("jable")
    monkeypatch.setattr(
        composition,
        "build_credential_records",
        lambda: (_ for _ in ()).throw(CredentialUnavailable("missing key")),
    )
    with pytest.raises(CredentialUnavailable):
        composition.source_factories(
            None, settings.BROWSER_FETCH_CONFIG, save_old_cookie, proxy_server=server
        )["jable"]().load_cookie_from_db()


def test_old_worker_cannot_downgrade_snapshot_after_key_rotation(runtime):
    from nassav.account_models import UserAccount
    from nassav.credential_rotation import rotate_credentials

    (first, _), records = runtime
    UserAccount.objects.create(user=first, role="admin")
    ref = records.resolve("jable", user_id=first.pk)
    lease = records.claim_refresh(
        ref, egress_profile="direct", browser_context="fixture-v1"
    )
    rotated = DjangoCredentialRecords(
        CredentialKeyring("k2", {"k1": b"a" * 32, "k2": b"b" * 32}), records.origins
    )
    rotate_credentials(rotated, first.pk, apply=True)
    with pytest.raises(CredentialUnavailable):
        records.publish_refresh(
            lease,
            {
                "cookie": "account_session=user-0; cf_clearance=new",
                "user_agent": "fixture-UA",
            },
            expires_at=timezone.now() + timedelta(minutes=5),
        )
    assert records.release_refresh(lease) == 1
    assert not SourceSessionSnapshot.objects.exclude(ciphertext="").exists()
    assert rotated.secret(ref)["cookie"].startswith("account_session=user-0")


def test_shared_playback_binds_system_reference_and_revocation_closes_session(
    runtime, settings, monkeypatch, resource_factory
):
    from uuid import uuid4
    from nassav.account_models import UserAccount
    from nassav.playback import records as playback
    from nassav.playback.contracts import PlaybackDescriptor, PlaybackStopped
    from nassav import composition

    (viewer, admin), records = runtime
    UserAccount.objects.create(user=admin, role="admin")
    system = records.write(
        admin.pk,
        "jable",
        {
            "expected_version": 0,
            "cookie": "cf_clearance=system",
            "user_agent": "fixture-UA",
            "request_id": str(uuid4()),
            "reason": "maintenance",
        },
        scope="system",
    )
    monkeypatch.setattr(composition, "build_credential_records", lambda: records)
    settings.SOURCE_CREDENTIALS_ENABLED = True
    resource = resource_factory(source="Jable")
    row = playback.submit(
        viewer.pk,
        "scoped-login",
        resource.avid,
        uuid4(),
        source_auth=composition.build_playback_source_binding(resource.avid),
    )
    assert row.library_grant["source_auth"]["credential_id"] == system["id"]
    assert row.library_grant["source_auth"]["credential_id"] != str(
        records.resolve("jable", user_id=viewer.pk).id
    )
    token = playback.claim(row.pk)
    playback.ready(
        token,
        PlaybackDescriptor(
            "https://media.example/master.m3u8",
            "https://jable.tv/videos/abc-001/",
            "fixture-UA",
            "jable",
            None,
            None,
        ),
    )
    row.refresh_from_db()
    assert row.state == "ready"
    records.write(
        admin.pk,
        "jable",
        {"expected_version": 1, "request_id": str(uuid4()), "reason": "security"},
        scope="system",
        revoke=True,
    )
    row.refresh_from_db()
    assert row.state == "closed" and not row.descriptor
    with pytest.raises(PlaybackStopped):
        playback.ready(
            token,
            PlaybackDescriptor(
                "https://media.example/master.m3u8",
                "https://jable.tv/videos/abc-001/",
                "fixture-UA",
                "jable",
                None,
                None,
            ),
        )


def test_account_disable_and_reactivation_cannot_resurrect_old_source_context(runtime):
    from uuid import uuid4
    from nassav.account_models import UserAccount
    from nassav.composition import build_account_management

    (first, admin), records = runtime
    UserAccount.objects.create(user=first, role="user")
    UserAccount.objects.create(user=admin, role="admin")
    scope = context(records, first.pk)
    assert scope.scope_key
    management = build_account_management()
    disabled = management.execute(
        admin.pk,
        "update",
        first.pk,
        {
            "expected_version": 1,
            "request_id": str(uuid4()),
            "reason": "security",
            "is_active": False,
        },
    )
    management.execute(
        admin.pk,
        "update",
        first.pk,
        {
            "expected_version": disabled["version"],
            "request_id": str(uuid4()),
            "reason": "maintenance",
            "is_active": True,
        },
    )
    with pytest.raises(CredentialUnavailable):
        scope.check()
    with pytest.raises(CredentialUnavailable):
        context(records, first.pk).load_session()


def test_cached_detail_authorization_queries_do_not_grow_per_candidate(runtime):
    (first, _), records = runtime
    source = Jable(facts_cache=build_provider_facts_cache())
    source.bind_credential_context(context(records, first.pk))
    assert source.credential_context.scope_key
    # Four checks before and after one bulk select/update; candidate count is 100.
    # Exact production SQL is intentionally measured rather than mocked per item.
    from django.test.utils import CaptureQueriesContext
    from django.db import connection

    lookup = SourceFactsLookup(source.facts_cache, source)
    with CaptureQueriesContext(connection) as single:
        lookup.read_details([("ABC-001", "")])
    with CaptureQueriesContext(connection) as many:
        lookup.read_details([(f"ABC-{index:03}", "") for index in range(100)])
    assert len(many) == len(single)


def test_completed_search_handle_is_rejected_after_credential_change(
    runtime, settings, monkeypatch, actor_factory
):
    from test_search_jobs import MemoryStore
    from nassav import search_jobs, search_job_views, composition
    from rest_framework.test import APIClient

    (first, _), records = runtime
    settings.SOURCE_CREDENTIALS_ENABLED = True
    settings.NASSAV_OPERATOR_USERNAME = first.username
    monkeypatch.setattr(composition, "build_credential_records", lambda: records)
    monkeypatch.setattr(search_jobs, "_publish", Mock())
    monkeypatch.setattr(search_jobs.run_search_job, "apply_async", Mock())
    store = MemoryStore()
    actor = actor_factory(name="Scoped actor")
    queued, _ = search_jobs.submit_search_job(
        {"entity_type": "actor", "entity_id": actor.pk, "source": "jable"},
        store=store,
        user_id=first.pk,
    )
    assert queued["query"]["source_context"]
    finished = store.save(
        {
            **queued,
            "state": "succeeded",
            "result": {
                "data": {"external_results": []},
                "pagination": {"page": 1, "page_size": 20},
            },
            "collected_results": [],
        }
    )
    records.write(
        first.pk,
        "jable",
        {
            "expected_version": 1,
            "cookie": "account_session=manual",
            "user_agent": "fixture-UA",
        },
    )
    with pytest.raises(search_jobs.SearchJobAccessExpired):
        search_jobs.get_search_job(queued["task_id"], store=store)
    assert store.get(queued["task_id"])["version"] == finished["version"]
    monkeypatch.setattr(
        search_job_views,
        "get_search_job",
        lambda task_id, **kwargs: search_jobs.get_search_job(
            task_id, store=store, **kwargs
        ),
    )
    client = APIClient()
    client.force_authenticate(first)
    token = search_jobs.search_job_token(queued["task_id"], user_id=first.pk)
    response = client.get(f"/nassav/api/search/jobs/{queued['task_id']}?token={token}")
    assert response.status_code == 410 and response.json()["data"] is None


@pytest.mark.django_db(transaction=True)
def test_concurrent_same_context_refresh_fetches_browser_once(runtime, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event, Lock
    from django.db import close_old_connections

    (first, _), records = runtime
    entered, waiter, finish = Event(), Event(), Event()
    count_lock = Lock()
    calls = []
    original_busy = records.refresh_busy

    def busy(*args, **kwargs):
        value = original_busy(*args, **kwargs)
        if value:
            waiter.set()
        return value

    monkeypatch.setattr(records, "refresh_busy", busy)

    def browser():
        with count_lock:
            calls.append(1)
        entered.set()
        assert finish.wait(timeout=10)
        return browser_result()

    def direct(url, *, session_override, timeout_seconds):
        return (
            private_result()
            if "cf_clearance=new" in session_override.cookie
            else replace(private_result(), html="denied", target_status=403)
        )

    def run():
        close_old_connections()
        try:
            return context(records, first.pk).fetch_browser_page(
                browser_result().final_url,
                browser,
                lambda html: "Private" in html,
                direct,
                10000,
            )
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        first_result = pool.submit(run)
        assert entered.wait(timeout=10)
        second_result = pool.submit(run)
        try:
            assert waiter.wait(timeout=10)
        finally:
            finish.set()
        assert first_result.result(timeout=10).ok
        assert second_result.result(timeout=10).ok
    assert calls == [1]
    assert not SourceSessionSnapshot.objects.exclude(refresh_owner=None).exists()
