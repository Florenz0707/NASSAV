import pytest
from django.core.cache import cache

from nassav.source.Jable import Jable


@pytest.mark.django_db
class TestJableSearchCache:
    def setup_method(self):
        cache.clear()

    def teardown_method(self):
        cache.clear()

    def test_search_uses_cache_when_enabled(self, settings, monkeypatch):
        settings.EXTERNAL_SOURCE_SEARCH_CACHE_ENABLED = True
        settings.EXTERNAL_SOURCE_SEARCH_CACHE_TTL_DEFAULT = 1800

        jable = Jable(proxy=None)
        calls = {"fetch": 0, "parse": 0}

        def fake_fetch_html(url, referer=None):
            _ = (url, referer)
            calls["fetch"] += 1
            return "<html>stub</html>"

        def fake_parse_search_results(html):
            _ = html
            calls["parse"] += 1
            return [
                {
                    "avid": "ABC-001",
                    "title": "title",
                    "detail_url": "https://jable.tv/videos/abc-001/",
                    "cover_url": "https://assets-cdn.jable.tv/abc.jpg",
                    "source": "Jable",
                    "metrics": {"views": 1},
                }
            ]

        monkeypatch.setattr(jable, "fetch_html", fake_fetch_html)
        monkeypatch.setattr(jable, "_parse_search_results", fake_parse_search_results)

        first = jable.search("abc", page=1)
        second = jable.search("abc", page=1)

        assert calls["fetch"] == 1
        assert calls["parse"] == 1
        assert first == second

    def test_search_force_refresh_bypasses_cache(self, settings, monkeypatch):
        settings.EXTERNAL_SOURCE_SEARCH_CACHE_ENABLED = True

        jable = Jable(proxy=None)
        calls = {"fetch": 0}

        def fake_fetch_html(url, referer=None):
            _ = (url, referer)
            calls["fetch"] += 1
            return "<html>stub</html>"

        def fake_parse_search_results(html):
            _ = html
            return [
                {
                    "avid": "ABC-002",
                    "title": "title",
                    "detail_url": "https://jable.tv/videos/abc-002/",
                    "cover_url": "https://assets-cdn.jable.tv/abc2.jpg",
                    "source": "Jable",
                    "metrics": {"views": 2},
                }
            ]

        monkeypatch.setattr(jable, "fetch_html", fake_fetch_html)
        monkeypatch.setattr(jable, "_parse_search_results", fake_parse_search_results)

        jable.search("abc", page=1)
        jable.search("abc", page=1)
        jable.search("abc", page=1, force_refresh=True)

        assert calls["fetch"] == 2

    def test_search_disables_cache_when_config_off(self, settings, monkeypatch):
        settings.EXTERNAL_SOURCE_SEARCH_CACHE_ENABLED = False

        jable = Jable(proxy=None)
        calls = {"fetch": 0}

        def fake_fetch_html(url, referer=None):
            _ = (url, referer)
            calls["fetch"] += 1
            return "<html>stub</html>"

        def fake_parse_search_results(html):
            _ = html
            return [
                {
                    "avid": "ABC-003",
                    "title": "title",
                    "detail_url": "https://jable.tv/videos/abc-003/",
                    "cover_url": "https://assets-cdn.jable.tv/abc3.jpg",
                    "source": "Jable",
                    "metrics": {"views": 3},
                }
            ]

        monkeypatch.setattr(jable, "fetch_html", fake_fetch_html)
        monkeypatch.setattr(jable, "_parse_search_results", fake_parse_search_results)

        jable.search("abc", page=1)
        jable.search("abc", page=1)

        assert calls["fetch"] == 2
