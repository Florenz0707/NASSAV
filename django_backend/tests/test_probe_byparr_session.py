"""Offline checks for the read-only P0 session probe."""

from datetime import datetime, timedelta, timezone

from nassav.page_fetching import PageFetchService
from nassav.source.Jable import Jable
from scripts.probe_byparr_session import cookie_header, valid_page


def test_cookie_header_selects_matching_domain_and_specific_path():
    future = (datetime.now(timezone.utc) + timedelta(days=1)).timestamp()
    past = (datetime.now(timezone.utc) - timedelta(days=1)).timestamp()
    items = [
        {"name": "sid", "value": "general", "domain": ".jable.tv", "path": "/"},
        {"name": "sid", "value": "detail", "domain": "jable.tv", "path": "/videos/"},
        {"name": "old", "value": "expired", "domain": "jable.tv", "expires": past},
        {"name": "other", "value": "wrong", "domain": "other.test"},
        {"name": "live", "value": "yes", "domain": "jable.tv", "expires": future},
    ]

    header = cookie_header(items, "jable.tv", "/videos/example/")

    assert header == "live=yes; sid=detail"


def test_probe_validation_rejects_challenge_and_wrong_site():
    source = Jable(page_fetcher=PageFetchService(None))
    url = "https://jable.tv/videos/example/"
    valid_html = '<script>var hlsUrl = "https://media.test/playlist.m3u8"</script>'

    assert valid_page(source, "detail", "EXAMPLE", url, url, valid_html) == "valid"
    assert (
        valid_page(source, "detail", "EXAMPLE", url, "https://other.test/", valid_html)
        == "wrong_site"
    )
    assert (
        valid_page(source, "detail", "EXAMPLE", url, url, "Just a moment...")
        == "challenge"
    )
