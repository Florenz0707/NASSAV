"""Offline fallback and content validation tests."""

from nassav.page_fetching.contracts import BrowserPageClient, FetchFailure, PageResult
from nassav.page_fetching.service import PageFetchService


class FakeBrowser(BrowserPageClient):
    def __init__(self, result):
        self.result = result
        self.calls = 0

    def fetch(self, url, *, timeout_ms):
        self.calls += 1
        return self.result


def test_browser_first_valid_page_skips_direct():
    browser = FakeBrowser(
        PageResult(
            html="<video>yes</video>",
            final_url="https://site.test/a",
            provider="byparr",
        )
    )
    service = PageFetchService(browser)
    result = service.fetch(
        "https://site.test/a",
        direct_fetch=lambda: 1 / 0,
        validator=lambda html: "<video>" in html,
        strategy="browser_first",
    )
    assert result.ok and browser.calls == 1


def test_direct_first_valid_page_skips_browser():
    browser = FakeBrowser(PageResult(failure=FetchFailure.CONNECTION))
    result = PageFetchService(browser).fetch(
        "https://site.test/a",
        direct_fetch=lambda: "valid",
        validator=lambda html: html == "valid",
        strategy="direct_first",
    )
    assert result.ok and browser.calls == 0


def test_challenge_and_mismatch_fall_back_once():
    browser = FakeBrowser(
        PageResult(
            html="Just a moment...", final_url="https://site.test/a", provider="byparr"
        )
    )
    calls = []
    result = PageFetchService(browser).fetch(
        "https://site.test/a",
        direct_fetch=lambda: calls.append(1) or "business",
        validator=lambda html: html == "business",
        strategy="browser_first",
    )
    assert result.ok and calls == [1] and browser.calls == 1
    browser.result = PageResult(
        html="business", final_url="https://other.test/a", provider="byparr"
    )
    assert (
        PageFetchService(browser)
        .fetch(
            "https://site.test/a",
            direct_fetch=lambda: None,
            validator=lambda _html: True,
            strategy="browser_first",
        )
        .failure
        == FetchFailure.EMPTY
    )


def test_connection_failure_skips_browser_for_remaining_candidates():
    browser = FakeBrowser(
        PageResult(failure=FetchFailure.CONNECTION, provider="byparr")
    )
    service = PageFetchService(browser)
    for path in ("a", "b"):
        service.fetch(
            f"https://site.test/{path}",
            direct_fetch=lambda: None,
            validator=lambda _html: True,
            strategy="browser_first",
        )
    assert browser.calls == 1
    service.reset_lookup()
    service.fetch(
        "https://site.test/c",
        direct_fetch=lambda: None,
        validator=lambda _html: True,
        strategy="browser_first",
    )
    assert browser.calls == 2


def test_direct_redirect_to_other_host_is_rejected():
    service = PageFetchService(None)
    result = service.fetch(
        "https://site.test/a",
        direct_fetch=lambda: PageResult(
            html="business", final_url="https://other.test/a", provider="direct"
        ),
        validator=lambda _html: True,
        strategy="direct_only",
    )
    assert result.failure == FetchFailure.PAGE_MISMATCH


def test_browser_connection_failure_is_scoped_to_one_lookup():
    browser = FakeBrowser(
        PageResult(failure=FetchFailure.CONNECTION, provider="byparr")
    )
    shared = PageFetchService(browser)
    first = shared.for_lookup()
    second = shared.for_lookup()
    first.fetch(
        "https://site.test/a",
        direct_fetch=lambda: None,
        validator=lambda _html: True,
        strategy="browser_first",
    )
    second.fetch(
        "https://site.test/b",
        direct_fetch=lambda: None,
        validator=lambda _html: True,
        strategy="browser_first",
    )
    assert browser.calls == 2


def test_disabled_session_reuse_keeps_direct_first_order_without_session_hooks():
    from unittest.mock import Mock

    browser = Mock()
    browser.fetch.return_value = PageResult(
        html="valid", final_url="https://example.test/page", provider="byparr"
    )
    direct = Mock(return_value="valid")
    handler = Mock()
    service = PageFetchService(browser, session_reuse_enabled=False)
    result = service.fetch(
        "https://example.test/page",
        direct_fetch=direct,
        validator=lambda html: html == "valid",
        strategy="direct_first",
        session_handler=handler,
        source="Jable",
        path_kind="detail",
    )
    assert result.ok and result.provider == "direct"
    direct.assert_called_once()
    browser.fetch.assert_not_called()
    handler.accept_browser_session.assert_not_called()
    handler.coordinate_browser_fallback.assert_not_called()
    service.session_reuse_enabled = True
    result = service.fetch(
        "https://example.test/page",
        direct_fetch=direct,
        validator=lambda html: html == "valid",
        strategy="direct_first",
        source="Jable",
        path_kind="detail",
    )
    assert result.ok and result.provider == "direct"
    assert direct.call_count == 2


def test_page_logs_show_direct_403_and_browser_completion_without_secrets(monkeypatch):
    from unittest.mock import Mock
    from nassav.page_fetching import service as service_module

    messages = []
    monkeypatch.setattr(
        service_module.logger,
        "info",
        lambda template, *values: messages.append(template.format(*values)),
    )
    browser = Mock()
    browser.fetch.return_value = PageResult(
        html="valid",
        final_url="https://example.test/page",
        provider="byparr",
        target_status=200,
        elapsed_ms=12,
    )
    service = PageFetchService(browser)
    result = service.fetch(
        "https://example.test/page",
        direct_fetch=lambda: PageResult(
            final_url="https://example.test/page",
            provider="direct",
            target_status=403,
            elapsed_ms=4,
        ),
        validator=lambda html: html == "valid",
        strategy="direct_first",
        source="Jable",
        path_kind="detail",
        request_id="sample",
    )
    assert result.ok
    assert any(
        "page_fetch_attempt" in line and "status=403" in line for line in messages
    )
    assert any("page_fetch " in line and "browser_calls=1" in line for line in messages)
    assert all("https://" not in line and "Cookie" not in line for line in messages)


def test_direct_first_falls_back_to_browser_when_reuse_is_disabled():
    from unittest.mock import Mock

    events = []
    browser = Mock()

    def browser_fetch(*args, **kwargs):
        events.append("browser")
        return PageResult(
            html="valid", final_url="https://example.test/page", provider="byparr"
        )

    browser.fetch.side_effect = browser_fetch

    def direct():
        events.append("direct")
        return PageResult(
            final_url="https://example.test/page", provider="direct", target_status=403
        )

    handler = Mock()
    result = PageFetchService(browser, session_reuse_enabled=False).fetch(
        "https://example.test/page",
        direct_fetch=direct,
        validator=lambda html: html == "valid",
        strategy="direct_first",
        session_handler=handler,
    )
    assert result.ok and events == ["direct", "browser"]
    handler.accept_browser_session.assert_not_called()
    handler.coordinate_browser_fallback.assert_not_called()
