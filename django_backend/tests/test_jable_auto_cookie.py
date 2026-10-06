"""Jable automatic Cookie API uses a validated, paired browser session."""

import importlib
from unittest.mock import Mock

import pytest
from curl_cffi.requests.exceptions import HTTPError
from nassav.models import SourceCookie
from nassav.page_fetching import PageFetchService, PageResult
from nassav.source.CookieRepository import source_cookie_repository
from nassav.source.Jable import Jable
from nassav.source.SourceManager import SourceManager

HOME = "https://jable.tv/"
LIST = '<div class="video-img-box"><a href="/videos/test-001/">TEST-001</a></div>'


@pytest.fixture
def automatic_source(monkeypatch, fake_session_store):
    browser = Mock(provider="byparr")
    browser.fetch.return_value = PageResult(
        html=LIST,
        final_url=HOME,
        provider="byparr",
        user_agent="Browser/test",
        cookies=(
            {
                "name": "session",
                "value": "verified",
                "domain": ".jable.tv",
                "path": "/",
            },
        ),
    )
    source = Jable(
        "http://proxy.test:8080",
        page_fetcher=PageFetchService(browser, session_reuse_enabled=False),
    )
    source.fetch_page = Mock(
        return_value=PageResult(
            html=LIST,
            final_url=HOME,
            provider="direct",
            target_status=200,
            elapsed_ms=10,
        )
    )
    legacy = Mock()
    legacy.get.side_effect = HTTPError("legacy homepage HTTP 403")
    module = importlib.import_module("nassav.source.SourceBase")
    monkeypatch.setattr(module.requests, "Session", Mock(return_value=legacy))
    manager = SourceManager.__new__(SourceManager)
    manager.sources = {"Jable": source}
    import nassav.http.source_views as views

    monkeypatch.setattr(views, "source_manager", manager)
    source_cookie_repository.invalidate_cookie("Jable")
    return source, browser, legacy


def post_auto(client):
    return client.post(
        "/nassav/api/source/cookie",
        data={"source": "Jable", "auto": True},
        content_type="application/json",
    )


@pytest.mark.django_db
def test_auto_api_uses_browser_when_legacy_homepage_is_403(client, automatic_source):
    source, browser, legacy = automatic_source
    response = post_auto(client)
    assert response.status_code == 200
    browser.fetch.assert_called_once_with(HOME, timeout_ms=60000)
    legacy.get.assert_not_called()
    record = SourceCookie.objects.get(source_name="jable")
    assert record.cookie == "session=verified"
    assert record.user_agent == "Browser/test"
    assert record.egress_profile
    assert source.fetch_page.call_args.kwargs["timeout_seconds"] == 3
    assert (
        source.fetch_page.call_args.kwargs["session_override"].user_agent
        == record.user_agent
    )


@pytest.mark.django_db
@pytest.mark.parametrize(
    "failure",
    [
        "challenge",
        "wrong_host",
        "missing_ua",
        "missing_cookies",
        "probe_403",
        "probe_slow",
    ],
)
def test_auto_rejects_unverified_session_without_replacing_manual_cookie(
    client, automatic_source, failure
):
    from dataclasses import replace

    source, browser, _ = automatic_source
    source_cookie_repository.set_cookie(
        "Jable", "manual=keep", user_agent="Manual/test"
    )
    before = source_cookie_repository.get_cookie_record("Jable")
    result = browser.fetch.return_value
    if failure == "challenge":
        browser.fetch.return_value = replace(
            result, html="<title>Just a moment...</title>"
        )
    elif failure == "wrong_host":
        browser.fetch.return_value = replace(result, final_url="https://other.test/")
    elif failure == "missing_ua":
        browser.fetch.return_value = replace(result, user_agent="")
    elif failure == "missing_cookies":
        browser.fetch.return_value = replace(result, cookies=())
    elif failure == "probe_403":
        source.fetch_page.return_value = replace(
            source.fetch_page.return_value, target_status=403
        )
    else:
        source.fetch_page.return_value = replace(
            source.fetch_page.return_value, elapsed_ms=3001
        )
    assert post_auto(client).status_code == 500
    assert source_cookie_repository.get_cookie_record("Jable") == before


@pytest.mark.django_db
@pytest.mark.parametrize("manual_action", ["update", "clear"])
def test_manual_change_during_probe_wins(client, automatic_source, manual_action):
    source, _, _ = automatic_source
    probe = source.fetch_page.return_value

    def competing_write(*args, **kwargs):
        source_cookie_repository.set_cookie(
            "Jable", "manual=new" if manual_action == "update" else ""
        )
        return probe

    source.fetch_page.side_effect = competing_write
    assert post_auto(client).status_code == 500
    saved = source_cookie_repository.get_cookie_record("Jable")
    assert saved.cookie == ("manual=new" if manual_action == "update" else "")
    assert not saved.user_agent


@pytest.mark.django_db
def test_lost_lease_cannot_save_session(automatic_source):
    source, browser, _ = automatic_source
    assert (
        source.set_cookie_auto(force_refresh=True, write_guard=lambda: False) is False
    )
    browser.fetch.assert_called_once()
    assert source_cookie_repository.get_cookie_record("Jable") is None


@pytest.mark.django_db
def test_existing_cookie_is_loaded_without_browser(automatic_source):
    source, browser, _ = automatic_source
    source_cookie_repository.set_cookie("Jable", "manual=keep")
    assert source.set_cookie_auto() is True
    browser.fetch.assert_not_called()
