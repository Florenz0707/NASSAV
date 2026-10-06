"""P1 session migration, versioning, cache, and request-snapshot contracts."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from importlib import import_module
from threading import Barrier, Event, Thread

import pytest
from curl_cffi import requests as cffi_requests
from django.core.cache import cache
from django.db import close_old_connections, connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone
from nassav.models import SourceCookie
from nassav.source.CookieRepository import (
    SourceCookieRecord,
    proxy_route_profile,
    source_cookie_repository,
)
from nassav.source.CookieRuntimeCache import source_cookie_runtime_cache
from nassav.source.Jable import Jable
from nassav.source.SourceManager import SourceManager


def save_browser_session(
    source="Jable", expected=None, cookie="session=one", ua="browser-UA"
):
    return source_cookie_repository.set_session_if_version(
        source,
        expected_updated_at=expected,
        cookie=cookie,
        user_agent=ua,
        expires_at=timezone.now() + timedelta(minutes=10),
        egress_profile=proxy_route_profile("http://proxy.test:8080"),
    )


@pytest.mark.django_db
def test_manual_overwrite_and_clear_remove_all_automatic_metadata(client):
    browser = save_browser_session()
    assert browser is not None
    assert browser.user_agent == "browser-UA"

    manager = SourceManager()
    assert manager.set_source_cookie("Jable", "manual=two")
    record = source_cookie_repository.get_cookie_record("Jable")
    assert record is not None
    assert record.cookie == "manual=two"
    assert record.user_agent is None
    assert record.expires_at is None
    assert record.egress_profile is None
    assert record.updated_at != browser.updated_at
    assert (
        client.get("/nassav/api/source/cookie").json()["data"][0]["cookie"]
        == "manual=two"
    )

    assert client.delete("/nassav/api/source/cookie?source=jable").status_code == 200
    cleared = source_cookie_repository.get_cookie_record("Jable")
    assert cleared is not None
    assert cleared.cookie == ""
    assert cleared.user_agent is None
    assert cleared.expires_at is None
    assert cleared.egress_profile is None


@pytest.mark.django_db
def test_late_browser_result_cannot_replace_manual_or_newer_session():
    old = source_cookie_repository.set_cookie("Jable", "manual=old")
    manual = source_cookie_repository.set_cookie("Jable", "manual=new")
    assert save_browser_session(expected=old.updated_at) is None
    assert source_cookie_repository.get_cookie("Jable") == "manual=new"

    browser = save_browser_session(expected=manual.updated_at)
    assert browser is not None
    assert (
        save_browser_session(expected=manual.updated_at, cookie="session=late") is None
    )
    latest = source_cookie_repository.get_cookie_record("Jable")
    assert latest == browser

    source_cookie_repository.set_cookie("Jable", "")
    assert (
        save_browser_session(expected=browser.updated_at, cookie="session=late") is None
    )
    assert source_cookie_repository.get_cookie("Jable") == ""


@pytest.mark.django_db
def test_unknown_route_is_rejected_and_identical_replay_keeps_version():
    assert (
        source_cookie_repository.set_session_if_version(
            "Jable",
            expected_updated_at=None,
            cookie="session=unverified",
            user_agent="browser-UA",
            expires_at=None,
            egress_profile=None,
        )
        is None
    )
    assert not SourceCookie.objects.exists()

    first = save_browser_session()
    assert first is not None
    replay = source_cookie_repository.set_session_if_version(
        "Jable",
        expected_updated_at=first.updated_at,
        cookie=first.cookie,
        user_agent=first.user_agent or "",
        expires_at=first.expires_at,
        egress_profile=first.egress_profile,
    )
    assert replay == first
    assert replay.updated_at == first.updated_at


@pytest.mark.django_db
def test_shared_and_runtime_cache_move_complete_versions_together():
    source_cookie_runtime_cache.clear()
    first = save_browser_session()
    assert first is not None
    manager_a = SourceManager()
    manager_b = SourceManager()
    assert manager_a.refresh_source_session("Jable") == first
    state = source_cookie_runtime_cache.get_state("Jable")
    assert state is not None and state.session == first

    second = save_browser_session(
        expected=first.updated_at, cookie="session=two", ua="second-UA"
    )
    assert second is not None
    assert manager_b.refresh_source_session("Jable") == second
    state = source_cookie_runtime_cache.get_state("Jable")
    assert state is not None and state.session == second
    assert manager_a.sources["Jable"].cookie == "session=one"
    assert manager_a.refresh_source_cookie("Jable") == "session=two"
    assert manager_a.sources["Jable"]._session_snapshot == second
    shared = cache.get("source_cookie:jable")
    assert shared["cookie"] == "session=two"
    assert shared["user_agent"] == "second-UA"
    assert shared["updated_at"] == second.updated_at


@pytest.mark.django_db
def test_stale_shared_cache_is_rejected_using_database_version():
    first = save_browser_session()
    assert first is not None
    source_cookie_repository.get_cookie_record("Jable")
    stale = cache.get("source_cookie:jable")
    second = source_cookie_repository.set_cookie("Jable", "manual=two")
    cache.set("source_cookie:jable", stale, timeout=3600)

    assert source_cookie_repository.get_cookie_record("Jable") == second
    assert cache.get("source_cookie:jable")["user_agent"] is None


def test_page_fetch_uses_one_snapshot_even_when_source_changes(monkeypatch):
    source = Jable()
    source.page_fetcher.session_reuse_enabled = True
    source.set_session(SourceCookieRecord("jable", "session=old", "v1", "old-UA"))
    entered = Event()
    continue_request = Event()
    captured = []
    original = source.fetch_html

    def delayed_fetch(url, referer=""):
        entered.set()
        assert continue_request.wait(3)
        return original(url, referer=referer)

    class Response:
        text = "valid body"
        url = "https://jable.tv/videos/example/"

        def raise_for_status(self):
            pass

    def fake_get(_url, **kwargs):
        captured.append(kwargs["headers"])
        return Response()

    monkeypatch.setattr(source, "fetch_html", delayed_fetch)
    monkeypatch.setattr(cffi_requests, "get", fake_get)
    result = []
    thread = Thread(
        target=lambda: result.append(
            source.fetch_page("https://jable.tv/videos/example/")
        )
    )
    thread.start()
    assert entered.wait(3)
    source.set_session(SourceCookieRecord("jable", "session=new", "v2", "new-UA"))
    continue_request.set()
    thread.join(3)

    assert not thread.is_alive()
    assert result[0].html == "valid body"
    assert captured[0]["Cookie"] == "session=old"
    assert captured[0]["User-Agent"] == "old-UA"


def test_expired_or_other_route_session_is_not_sent(monkeypatch):
    source = Jable()
    source.page_fetcher.session_reuse_enabled = True
    captured = []

    class Response:
        text = "body"
        url = "https://jable.tv/videos/example/"

        def raise_for_status(self):
            pass

    def fake_get(_url, **kwargs):
        captured.append(kwargs["headers"])
        return Response()

    monkeypatch.setattr(cffi_requests, "get", fake_get)
    expired = SourceCookieRecord(
        "jable",
        "session=expired",
        "v1",
        "expired-UA",
        timezone.now() - timedelta(seconds=1),
    )
    source.set_session(expired)
    source.fetch_page("https://jable.tv/videos/example/")
    source.set_session(
        SourceCookieRecord(
            "jable", "session=other", "v2", "other-UA", None, "wrong-route"
        )
    )
    source.fetch_page("https://jable.tv/videos/example/")

    assert all("Cookie" not in headers for headers in captured)
    assert all(headers.get("User-Agent") != "expired-UA" for headers in captured)
    assert all(headers.get("User-Agent") != "other-UA" for headers in captured)


def test_page_error_does_not_log_cookie_or_proxy_credentials(monkeypatch):
    source = Jable(proxy="http://account:proxy-secret@localhost:8080")
    source.set_cookie("session=private")
    messages = []

    def fake_get(_url, **_kwargs):
        raise RuntimeError("session=private proxy-secret")

    monkeypatch.setattr(cffi_requests, "get", fake_get)
    monkeypatch.setattr(
        import_module("nassav.source.SourceBase").logger, "error", messages.append
    )
    source.fetch_page("https://jable.tv/videos/example/")

    assert source.last_error_code == "RuntimeError"
    assert messages
    assert all("session=private" not in message for message in messages)
    assert all("proxy-secret" not in message for message in messages)


def test_proxy_route_profile_includes_identity_without_exposing_it():
    first = proxy_route_profile("http://account:secret@127.0.0.1:8080")
    equivalent = proxy_route_profile("http://account:secret@localhost:8080")
    different = proxy_route_profile("http://account:changed@localhost:8080")
    assert first == equivalent
    assert first != different
    assert first is not None and len(first) == 64
    assert "secret" not in first
    assert "session=private" not in repr(
        SourceCookieRecord("jable", "session=private", user_agent="private-UA")
    )


@pytest.mark.django_db(transaction=True)
def test_two_concurrent_refreshes_accept_only_one_version():
    initial = source_cookie_repository.set_cookie("Jable", "manual=initial")
    barrier = Barrier(3)

    def attempt(cookie):
        close_old_connections()
        barrier.wait()
        try:
            return save_browser_session(expected=initial.updated_at, cookie=cookie)
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(attempt, "session=first")
        second = pool.submit(attempt, "session=second")
        barrier.wait()
        results = [first.result(), second.result()]
    assert sum(record is not None for record in results) == 1
    persisted = source_cookie_repository.get_cookie_record("Jable")
    assert persisted is not None
    assert persisted.cookie in {"session=first", "session=second"}
    assert persisted.user_agent == "browser-UA"


@pytest.mark.django_db(transaction=True)
def test_legacy_cookie_survives_additive_session_migration():
    old_target = [("nassav", "0020_increase_translated_title_length")]
    new_target = [("nassav", "0021_sourcecookie_session_metadata")]
    executor = MigrationExecutor(connection)
    try:
        executor.migrate(old_target)
        legacy_model = executor.loader.project_state(old_target).apps.get_model(
            "nassav", "SourceCookie"
        )
        legacy_model.objects.create(source_name="Legacy", cookie="unchanged=value")
        before_count = legacy_model.objects.count()
        executor = MigrationExecutor(connection)
        executor.migrate(new_target)
        row = SourceCookie.objects.get(source_name="Legacy")
        assert SourceCookie.objects.count() == before_count
        assert row.cookie == "unchanged=value"
        assert row.user_agent is None
        assert row.expires_at is None
        assert row.egress_profile is None
    finally:
        MigrationExecutor(connection).migrate(new_target)
