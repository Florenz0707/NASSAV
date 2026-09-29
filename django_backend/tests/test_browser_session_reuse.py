"""P2 offline contracts for direct classification and verified browser sessions."""

from datetime import timedelta
from importlib import import_module

import pytest
from curl_cffi.requests.exceptions import HTTPError, Timeout
from django.utils import timezone
from nassav.page_fetching import (
    BrowserPageClient,
    FetchFailure,
    PageFetchService,
    PageResult,
)
from nassav.page_fetching.session import candidate_for_page
from nassav.source.CookieRepository import proxy_route_profile, source_cookie_repository
from nassav.source.Jable import Jable
from nassav.source.MissAV import MissAV

JABLE_URL = "https://jable.tv/videos/jur-466/"
JABLE_HTML = '<title>JUR-466 Sample - Jable.TV</title><script>var hlsUrl = "https://video.test/master.m3u8";</script>'
MISSAV_HTML = '<meta property="og:title" content="IPZZ-912 Sample">m3u8|abc123|com|surrit|https|video'
PROXY = "http://user:secret@localhost:8080"


class FakeBrowser(BrowserPageClient):
    provider = "byparr"

    def __init__(self, html=JABLE_HTML, *, url=JABLE_URL, cookies=(), ua="browser-UA"):
        self.result = PageResult(
            html=html,
            final_url=url,
            provider="byparr",
            cookies=cookies,
            user_agent=ua,
            provider_status=200,
        )
        self.calls = 0

    def fetch(self, url, *, timeout_ms):
        self.calls += 1
        return self.result


def browser_cookie(*, domain=".jable.tv", path="/", expires=None):
    return {
        "name": "session",
        "value": "valid",
        "domain": domain,
        "path": path,
        "expires": expires or (timezone.now() + timedelta(minutes=10)).timestamp(),
    }


class DirectResponse:
    def __init__(self, *, status=200, html=JABLE_HTML, url=JABLE_URL):
        self.status_code = status
        self.text = html
        self.url = url

    def raise_for_status(self):
        if self.status_code >= 400:
            raise HTTPError("HTTP response", response=self)


def test_cookie_candidate_filters_scope_expiry_and_ambiguous_names():
    result = PageResult(
        user_agent="browser-UA",
        cookies=(
            browser_cookie(domain="other.test"),
            browser_cookie(path="/videos/bad"),
            browser_cookie(path="/videos", expires=1),
            browser_cookie(domain=".jable.tv", path="/"),
            {**browser_cookie(domain="jable.tv", path="/videos"), "value": "best"},
            {"name": "other", "value": "kept", "domain": "jable.tv", "path": "/"},
        ),
    )
    candidate = candidate_for_page(JABLE_URL, result)
    assert candidate is not None
    assert candidate.cookie == "other=kept; session=best"
    assert candidate.user_agent == "browser-UA"
    assert candidate.expires_at is not None
    conflicting = PageResult(
        user_agent="browser-UA",
        cookies=(browser_cookie(), {**browser_cookie(), "value": "different"}),
    )
    assert candidate_for_page(JABLE_URL, conflicting) is None
    assert (
        candidate_for_page(JABLE_URL, PageResult(cookies=(browser_cookie(),))) is None
    )


def test_direct_page_reports_target_status_final_url_and_timeout(monkeypatch):
    source = Jable(page_fetcher=PageFetchService(None))
    direct_module = import_module("nassav.source.SourceBase")
    monkeypatch.setattr(
        direct_module.requests,
        "get",
        lambda *_a, **_k: DirectResponse(
            status=403, html="denied", url="https://jable.tv/challenge"
        ),
    )
    denied = source.fetch_page(JABLE_URL)
    assert denied.failure == FetchFailure.TARGET_HTTP
    assert denied.target_status == 403
    assert denied.final_url == "https://jable.tv/challenge"
    assert denied.elapsed_ms >= 0
    assert source.last_error_code == 403

    def timed_out(*_args, **_kwargs):
        raise Timeout("timeout")

    monkeypatch.setattr(direct_module.requests, "get", timed_out)
    timeout = source.fetch_page(JABLE_URL)
    assert timeout.failure == FetchFailure.TIMEOUT
    assert timeout.target_status is None


@pytest.mark.django_db
def test_browser_first_persists_only_after_verified_probe_and_replay_is_idempotent(
    monkeypatch,
):
    browser = FakeBrowser(cookies=(browser_cookie(),))
    source = Jable(proxy=PROXY, page_fetcher=PageFetchService(browser))
    seen = []

    def direct_get(_url, **kwargs):
        seen.append(kwargs)
        return DirectResponse()

    monkeypatch.setattr(
        import_module("nassav.source.SourceBase").requests, "get", direct_get
    )
    assert source.get_html("JUR-466") == JABLE_HTML
    saved = source_cookie_repository.get_cookie_record("Jable")
    assert saved is not None
    assert saved.cookie == "session=valid"
    assert saved.user_agent == "browser-UA"
    assert saved.egress_profile == proxy_route_profile(PROXY)
    assert browser.calls == 1 and len(seen) == 1
    assert seen[0]["headers"]["Cookie"] == "session=valid"
    assert seen[0]["headers"]["User-Agent"] == "browser-UA"
    assert seen[0]["timeout"] == 3
    assert seen[0]["impersonate"] == "chrome110"

    assert source.get_html("JUR-466") == JABLE_HTML
    assert browser.calls == 2 and len(seen) == 1
    assert (
        source_cookie_repository.get_cookie_record("Jable").updated_at
        == saved.updated_at
    )


@pytest.mark.django_db
def test_direct_first_uses_warm_snapshot_without_browser_and_cold_403_falls_back(
    monkeypatch, settings
):
    settings.SOURCE_CONFIG = {
        **settings.SOURCE_CONFIG,
        "jable": {"browser_fetch_strategy": "direct_first"},
    }
    browser = FakeBrowser(cookies=(browser_cookie(),))
    source = Jable(proxy=PROXY, page_fetcher=PageFetchService(browser))
    calls = []

    def direct_get(_url, **kwargs):
        calls.append(kwargs["headers"])
        if len(calls) == 1:
            return DirectResponse(status=403, html="denied")
        return DirectResponse()

    monkeypatch.setattr(
        import_module("nassav.source.SourceBase").requests, "get", direct_get
    )
    assert source.get_html("JUR-466") == JABLE_HTML
    assert browser.calls == 1
    assert len(calls) == 2  # one cold direct, one bounded browser-session probe
    assert "Cookie" not in calls[0]
    assert calls[1]["Cookie"] == "session=valid"

    assert source.get_html("JUR-466") == JABLE_HTML
    assert browser.calls == 1
    assert len(calls) == 3
    assert calls[2]["Cookie"] == "session=valid"
    assert calls[2]["User-Agent"] == "browser-UA"


@pytest.mark.django_db
def test_failed_probe_keeps_valid_browser_page_without_persisting(monkeypatch):
    browser = FakeBrowser(cookies=(browser_cookie(),))
    source = Jable(proxy=PROXY, page_fetcher=PageFetchService(browser))
    monkeypatch.setattr(
        import_module("nassav.source.SourceBase").requests,
        "get",
        lambda *_a, **_k: DirectResponse(status=403, html="denied"),
    )
    assert source.get_html("JUR-466") == JABLE_HTML
    assert source_cookie_repository.get_cookie_record("Jable") is None
    assert browser.calls == 1


@pytest.mark.django_db
def test_invalid_browser_page_and_direct_only_never_persist(monkeypatch):
    browser = FakeBrowser(
        html="Just a moment...",
        cookies=(browser_cookie(),),
    )
    source = Jable(proxy=PROXY, page_fetcher=PageFetchService(browser))
    calls = []
    monkeypatch.setattr(
        import_module("nassav.source.SourceBase").requests,
        "get",
        lambda *_a, **_k: calls.append(1) or DirectResponse(status=403, html="denied"),
    )
    source.page_fetcher.fetch(
        JABLE_URL,
        direct_fetch=lambda: source.fetch_page(JABLE_URL),
        validator=source._is_detail_page_html,
        strategy="browser_first",
        session_handler=source,
    )
    assert len(calls) == 1
    assert source_cookie_repository.get_cookie_record("Jable") is None

    source.page_fetcher.fetch(
        JABLE_URL,
        direct_fetch=lambda: source.fetch_page(JABLE_URL),
        validator=source._is_detail_page_html,
        strategy="direct_only",
        session_handler=source,
    )
    assert browser.calls == 1
    assert len(calls) == 2
    assert source_cookie_repository.get_cookie_record("Jable") is None


@pytest.mark.django_db
def test_missav_browser_page_uses_same_probe_and_business_validator(monkeypatch):
    url = "https://missav.ai/cn/ipzz-912-chinese-subtitle"
    browser = FakeBrowser(
        html=MISSAV_HTML,
        url=url,
        cookies=({**browser_cookie(domain="missav.ai"), "name": "clearance"},),
    )
    source = MissAV(proxy=PROXY, page_fetcher=PageFetchService(browser))
    monkeypatch.setattr(
        import_module("nassav.source.SourceBase").requests,
        "get",
        lambda *_a, **_k: DirectResponse(html=MISSAV_HTML, url=url),
    )
    assert source.get_html("IPZZ-912") == MISSAV_HTML
    saved = source_cookie_repository.get_cookie_record("MissAV")
    assert saved is not None and saved.cookie == "clearance=valid"
    assert browser.calls == 1


@pytest.mark.django_db
def test_late_browser_result_cannot_replace_manual_cookie(monkeypatch):
    browser = FakeBrowser(cookies=(browser_cookie(),))
    source = Jable(proxy=PROXY, page_fetcher=PageFetchService(browser))
    source_cookie_repository.set_cookie("Jable", "manual=before")

    def fetch_and_update(url, *, timeout_ms):
        source_cookie_repository.set_cookie("Jable", "manual=after")
        return browser.result

    monkeypatch.setattr(browser, "fetch", fetch_and_update)
    monkeypatch.setattr(
        import_module("nassav.source.SourceBase").requests,
        "get",
        lambda *_a, **_k: DirectResponse(),
    )
    assert source.get_html("JUR-466") == JABLE_HTML
    assert source_cookie_repository.get_cookie("Jable") == "manual=after"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "reason",
    ["wrong_site", "invalid_page", "expired_cookie", "missing_ua", "wrong_domain"],
)
def test_invalid_browser_candidates_do_not_write(monkeypatch, reason):
    browser = FakeBrowser(cookies=(browser_cookie(),))
    if reason == "wrong_site":
        browser.result = PageResult(
            html=JABLE_HTML,
            final_url="https://other.test/videos/jur-466/",
            provider="byparr",
            cookies=(browser_cookie(),),
            user_agent="browser-UA",
        )
    elif reason == "invalid_page":
        browser.result = PageResult(
            html="<html>not a detail page</html>",
            final_url=JABLE_URL,
            provider="byparr",
            cookies=(browser_cookie(),),
            user_agent="browser-UA",
        )
    elif reason == "expired_cookie":
        browser.result = PageResult(
            html=JABLE_HTML,
            final_url=JABLE_URL,
            provider="byparr",
            cookies=(browser_cookie(expires=1),),
            user_agent="browser-UA",
        )
    elif reason == "missing_ua":
        browser.result = PageResult(
            html=JABLE_HTML,
            final_url=JABLE_URL,
            provider="byparr",
            cookies=(browser_cookie(),),
        )
    else:
        browser.result = PageResult(
            html=JABLE_HTML,
            final_url=JABLE_URL,
            provider="byparr",
            cookies=(browser_cookie(domain="other.test"),),
            user_agent="browser-UA",
        )
    source = Jable(proxy=PROXY, page_fetcher=PageFetchService(browser))
    direct_calls = []
    monkeypatch.setattr(
        import_module("nassav.source.SourceBase").requests,
        "get",
        lambda *_a, **_k: (
            direct_calls.append(1) or DirectResponse(status=403, html="denied")
        ),
    )
    source.page_fetcher.fetch(
        JABLE_URL,
        direct_fetch=lambda: source.fetch_page(JABLE_URL),
        validator=source._is_detail_page_html,
        strategy="browser_first",
        session_handler=source,
    )
    assert source_cookie_repository.get_cookie_record("Jable") is None
    assert (
        len(direct_calls) == 1
        if reason in {"wrong_site", "invalid_page"}
        else len(direct_calls) == 0
    )


@pytest.mark.django_db
def test_unverified_browser_route_never_persists(monkeypatch):
    browser = FakeBrowser(cookies=(browser_cookie(),))
    source = Jable(page_fetcher=PageFetchService(browser))
    direct_calls = []
    monkeypatch.setattr(
        import_module("nassav.source.SourceBase").requests,
        "get",
        lambda *_a, **_k: direct_calls.append(1) or DirectResponse(),
    )
    assert source.get_html("JUR-466") == JABLE_HTML
    assert direct_calls == []
    assert source_cookie_repository.get_cookie_record("Jable") is None


def test_embedded_challenge_script_does_not_reject_valid_missav_content():
    html = MISSAV_HTML + '<script src="/cdn-cgi/challenge-platform/x"></script>'
    assert not PageFetchService.is_challenge(html)
    assert PageFetchService.is_challenge("<div>Just a moment...</div>")


@pytest.mark.django_db
def test_direct_404_may_fall_back_without_refreshing_shared_session(monkeypatch):
    browser = FakeBrowser(cookies=(browser_cookie(),))
    source = Jable(proxy=PROXY, page_fetcher=PageFetchService(browser))
    direct_calls = []
    monkeypatch.setattr(
        import_module("nassav.source.SourceBase").requests,
        "get",
        lambda *_a, **_k: (
            direct_calls.append(1) or DirectResponse(status=404, html="not found")
        ),
    )
    result = source.page_fetcher.fetch(
        JABLE_URL,
        direct_fetch=lambda: source.fetch_page(JABLE_URL),
        validator=source._is_detail_page_html,
        strategy="direct_first",
        session_handler=source,
    )
    assert result.ok and result.provider == "byparr"
    assert direct_calls == [1]
    assert browser.calls == 1
    assert source_cookie_repository.get_cookie_record("Jable") is None


def test_http_200_challenge_has_different_failure_from_403(monkeypatch):
    source = Jable(page_fetcher=PageFetchService(None))
    monkeypatch.setattr(
        import_module("nassav.source.SourceBase").requests,
        "get",
        lambda *_a, **_k: DirectResponse(html="Just a moment..."),
    )
    result = source.page_fetcher.fetch(
        JABLE_URL,
        direct_fetch=lambda: source.fetch_page(JABLE_URL),
        validator=source._is_detail_page_html,
        strategy="direct_only",
    )
    assert result.target_status == 200
    assert result.failure == FetchFailure.CHALLENGE


@pytest.mark.django_db
def test_probe_over_budget_does_not_persist_but_returns_browser_page(monkeypatch):
    browser = FakeBrowser(cookies=(browser_cookie(),))
    source = Jable(proxy=PROXY, page_fetcher=PageFetchService(browser))
    monkeypatch.setattr(
        source,
        "fetch_page",
        lambda *_args, **_kwargs: PageResult(
            html=JABLE_HTML,
            final_url=JABLE_URL,
            provider="direct",
            target_status=200,
            elapsed_ms=3001,
        ),
    )
    assert source.get_html("JUR-466") == JABLE_HTML
    assert source_cookie_repository.get_cookie_record("Jable") is None
