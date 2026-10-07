"""Offline Source behavior after browser fetching migration."""

from unittest.mock import Mock, patch

from nassav.page_fetching import BrowserPageClient, PageFetchService, PageResult
from nassav.source.Jable import Jable
from nassav.source.MissAV import MissAV
from nassav.source.SourceManager import SourceManager

MISSAV_HTML = '<meta property="og:title" content="IPZZ-912 Sample">m3u8|abc123|com|surrit|https|video'
JABLE_DETAIL = '<title>JUR-466 Sample - Jable.TV</title><script>var hlsUrl = "https://video.test/master.m3u8";</script>'
JABLE_LIST = '<div class="video-img-box"><div class="img-box"><a href="/videos/jur-466/"><img src="https://assets-cdn.jable.tv/jur.jpg"></a></div><h6 class="title"><a href="/videos/jur-466/">JUR-466 Sample</a></h6><p class="sub-title">1,234 56</p></div>'


class FakeBrowser(BrowserPageClient):
    def __init__(self, html, *, cookies=()):
        self.html = html
        self.cookies = cookies
        self.urls = []

    def fetch(self, url, *, timeout_ms):
        self.urls.append(url)
        return PageResult(
            html=self.html, final_url=url, provider="byparr", cookies=self.cookies
        )


def test_missav_candidates_and_shared_validation():
    browser = FakeBrowser("<html>MissAV home</html>")
    source = MissAV(page_fetcher=PageFetchService(browser))
    source.fetch_html = Mock(side_effect=[None, None, MISSAV_HTML])
    with patch("time.sleep"):
        assert source.get_html("IPZZ-912") == MISSAV_HTML
    assert len(browser.urls) == 3
    assert browser.urls == [
        "https://missav.ai/cn/ipzz-912",
        "https://missav.ai/cn/ipzz-912-chinese-subtitle",
        "https://missav.ai/ipzz-912-chinese-subtitle",
    ]
    assert source.fetch_html.call_count == 3


def test_missav_valid_browser_skips_direct():
    browser = FakeBrowser(MISSAV_HTML)
    source = MissAV(page_fetcher=PageFetchService(browser))
    source.fetch_html = Mock(side_effect=AssertionError("unexpected direct fetch"))
    assert source.get_html("IPZZ-912") == MISSAV_HTML
    assert browser.urls == ["https://missav.ai/cn/ipzz-912"]


def test_missav_subtitle_fallback_after_invalid_plain_page():
    browser = FakeBrowser("")
    plain = "https://missav.ai/cn/ipzz-912"
    subtitle = plain + "-chinese-subtitle"
    browser.fetch = Mock(
        side_effect=[
            PageResult(
                html="<html>wrong page</html>", final_url=plain, provider="byparr"
            ),
            PageResult(html=MISSAV_HTML, final_url=subtitle, provider="byparr"),
        ]
    )
    source = MissAV(page_fetcher=PageFetchService(browser))
    source.fetch_html = Mock(return_value=None)
    with patch("time.sleep"):
        assert source.get_html("IPZZ-912") == MISSAV_HTML
    assert [call.args[0] for call in browser.fetch.call_args_list] == [
        plain,
        subtitle,
    ]


def test_jable_detail_and_search_fallback():
    browser = FakeBrowser(JABLE_DETAIL)
    source = Jable(page_fetcher=PageFetchService(browser))
    source.fetch_html = Mock(return_value=None)
    assert source.get_html("JUR-466") == JABLE_DETAIL
    browser.html = JABLE_LIST
    result = source.search("JUR-466", force_refresh=True)
    assert result and result[0]["avid"] == "JUR-466"


def test_jable_valid_direct_skips_browser(settings):
    settings.SOURCE_CONFIG = {
        **settings.SOURCE_CONFIG,
        "jable": {"browser_fetch_strategy": "direct_first"},
    }
    browser = FakeBrowser("bad")
    source = Jable(page_fetcher=PageFetchService(browser))
    source.fetch_html = Mock(return_value=JABLE_DETAIL)
    assert source.get_html("JUR-466") == JABLE_DETAIL
    assert browser.urls == []


def test_jable_valid_empty_listing_and_challenge_rejected():
    source = Jable(page_fetcher=PageFetchService(None))
    assert source._is_listing_page_html("<form>No results</form>")
    assert not source._is_listing_page_html("Just a moment...")


def test_missav_browser_cookie_save_uses_manager_cache(db):
    browser = FakeBrowser(
        "<html>MissAV home</html>",
        cookies=(
            {"name": "cf_clearance", "value": "good", "domain": ".missav.ai"},
            {"name": "foreign", "value": "bad", "domain": "other.test"},
        ),
    )
    manager = SourceManager.__new__(SourceManager)
    source = MissAV(
        page_fetcher=PageFetchService(browser),
        cookie_saver=lambda value: manager.set_source_cookie("MissAV", value),
    )
    manager.sources = {"MissAV": source}
    assert source.set_cookie_auto(force_refresh=True)
    assert source.cookie == "cf_clearance=good"
    assert manager.refresh_source_cookie("MissAV") == "cf_clearance=good"
    browser.cookies = ()
    assert not source.set_cookie_auto(force_refresh=True)
    assert manager.refresh_source_cookie("MissAV") == "cf_clearance=good"


def test_manager_injects_configured_browser(settings):
    from nassav.page_fetching import BrowserFetchConfig

    settings.SOURCE_CONFIG = {
        "missav": {"weight": 1},
        "jable": {"weight": 1},
    }
    settings.BROWSER_FETCH_CONFIG = BrowserFetchConfig(
        enabled=True,
        provider="byparr",
        url="http://127.0.0.1:8192",
        timeout_ms=60000,
    )
    settings.PROXY_ENABLED = True
    settings.PROXY_URL = "http://127.0.0.1:7890"
    manager = SourceManager()
    for name in ("MissAV", "Jable"):
        browser = manager.sources[name].page_fetcher.browser
        assert browser.provider == "byparr"
        assert browser.client._request_headers() == {
            "X-Proxy-Server": "http://host.docker.internal:7890"
        }

    settings.PROXY_ENABLED = False
    direct_manager = SourceManager()
    for name in ("MissAV", "Jable"):
        assert (
            direct_manager.sources[name].page_fetcher.browser.client._request_headers()
            == {}
        )


def test_source_direct_redirect_is_rejected():
    source = MissAV(page_fetcher=PageFetchService(None))

    def redirected(_url, referer=""):
        source.last_final_url = "https://other.test/"
        return MISSAV_HTML

    source.fetch_html = redirected
    with patch("time.sleep"):
        assert source.get_html("IPZZ-912") is None
