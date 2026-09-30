"""Offline validation of the read-only P5 Jable prescreen selector."""

from scripts.probe_p5_jable import detail_paths


def test_detail_paths_keep_only_same_site_detail_pages():
    html = """
    <a href="/videos/lulu-450/">one</a>
    <a href="https://jable.tv/videos/lulu-449/">two</a>
    <a href="/videos/lulu-450/">duplicate</a>
    <a href="https://other.test/videos/foreign/">other</a>
    <a href="//other.test/videos/foreign/">protocol relative</a>
    <a href="/videos/../../../admin/">path traversal</a>
    <a href="/videos/query/?token=secret">query</a>
    <a href="/search/example/">listing</a>
    """
    assert detail_paths(html, "jable.tv") == [
        "/videos/lulu-449/",
        "/videos/lulu-450/",
    ]
