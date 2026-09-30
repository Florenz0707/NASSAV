"""Offline checks for MissAV P5 read-only sample discovery."""

from scripts.probe_p5_missav import detail_candidates


def test_detail_candidates_only_accept_same_site_avid_paths():
    html = """
    <a href="/cn/fthtd-228-chinese-subtitle">first</a>
    <a href="https://missav.ai/fc2-ppv-1234567">second</a>
    <a href="/cn/fthtd-228-chinese-subtitle">duplicate</a>
    <a href="https://other.test/cn/fthtd-229">foreign</a>
    <a href="//other.test/cn/fthtd-230">foreign protocol relative</a>
    <a href="/cn/fthtd-231?token=secret">query</a>
    <a href="/cn/../../../admin">traversal</a>
    <a href="/cn/new">listing</a>
    <a href="javascript:/cn/fthtd-232">script</a>
    """
    assert detail_candidates(html, "missav.ai") == [
        ("/cn/fthtd-228-chinese-subtitle", "FTHTD-228"),
        ("/fc2-ppv-1234567", "FC2-PPV-1234567"),
    ]
