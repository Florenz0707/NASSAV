"""Offline contract checks for the isolated media A/B probe."""

from unittest.mock import Mock

import pytest
import requests
from scripts.probe_byparr_media import MediaSession, arm_order


def test_arm_order_is_balanced_and_reversed_in_second_window():
    first = [arm_order(index, "W1") for index in range(1, 21)]
    second = [arm_order(index, "W2") for index in range(1, 21)]
    assert first.count((False, True)) == first.count((True, False)) == 10
    assert all(a == tuple(reversed(b)) for a, b in zip(first, second, strict=True))


@pytest.mark.parametrize("block_media", [False, True])
def test_session_changes_only_media_flag_and_captures_timing(monkeypatch, block_media):
    response = Mock()
    response.json.return_value = {"experimentTimings": {"navigation_ms": 12}}
    post = Mock(return_value=response)
    monkeypatch.setattr(requests.Session, "post", post)
    session = MediaSession()
    session.block_media = block_media
    body = {"cmd": "request.get", "url": "https://example.test", "maxTimeout": 60000}
    assert session.post("http://isolated.test/v1", json=body, timeout=70) is response
    assert post.call_args.kwargs == {
        "json": {**body, "blockMedia": block_media},
        "timeout": 70,
    }
    assert "blockMedia" not in body
    assert session.timings == {"navigation_ms": 12}
    assert not session.trust_env


def test_invalid_response_does_not_reuse_previous_request_timing(monkeypatch):
    response = Mock()
    response.json.side_effect = ValueError("not JSON")
    monkeypatch.setattr(requests.Session, "post", Mock(return_value=response))
    session = MediaSession()
    session.timings = {"navigation_ms": 99}
    session.post("http://isolated.test/v1", json={})
    assert session.timings == {}


def test_summary_counts_failures_and_includes_their_latency():
    from scripts.probe_byparr_media import summarize

    rows = [
        {"valid": True, "client_ms": 10, "timings": {"navigation_ms": 2}},
        {"valid": False, "client_ms": 60000, "timings": {"navigation_ms": 59000}},
    ]
    assert summarize(rows) == {
        "attempts": 2,
        "valid": 1,
        "p50_ms": 30005,
        "p95_ms": 60000,
        "stage_medians_ms": {"navigation_ms": 29501},
    }
    assert summarize([]) == {"attempts": 0, "valid": 0}


@pytest.mark.parametrize(
    "url,html",
    [
        (
            "https://jable.tv/videos/ipzz-912/",
            '<meta property="og:image" content="https://assets.test/cover.jpg"><title>IPZZ-912 Video</title><script>var hlsUrl = "https://video.test/master.m3u8";</script>',
        ),
        (
            "https://missav.ai/cn/ipzz-912",
            '<meta property="og:title" content="IPZZ-912 Video">m3u8|abc123|com|surrit|https|video',
        ),
    ],
)
def test_business_wait_requires_requested_title_and_complete_media_marker(url, html):
    from scripts.byparr.business_ready import has_business_content

    assert has_business_content(html, url)
    assert not has_business_content(html.replace("IPZZ-912", "IPZZ-9120"), url)
    assert not has_business_content(
        html.replace("hlsUrl", "partial").replace("m3u8|", "partial|"), url
    )
    assert not has_business_content("<title>Just a moment...</title>", url)
    if "jable.tv" in url:
        assert not has_business_content(html.replace("og:image", "missing:image"), url)
    assert not has_business_content(
        html, url.replace(".tv", ".test").replace(".ai", ".test")
    )


def test_business_wait_does_not_apply_to_listing_or_unrecognized_host():
    from scripts.byparr.business_ready import detail_identity

    assert detail_identity("https://jable.tv/latest-updates/") is None
    assert detail_identity("https://missav.ai/") is None
    assert detail_identity("https://other.test/cn/ipzz-912") is None
