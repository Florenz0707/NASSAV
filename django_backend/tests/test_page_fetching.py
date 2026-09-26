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
