"""External search image routing and bounded CDN downloads."""

from unittest.mock import Mock

from nassav.recommendation.cover_cache import RecommendationCoverCacheService
from nassav.source import Jable, MissAV


def test_source_specific_image_allowlist():
    missav = RecommendationCoverCacheService(MissAV())
    jable = RecommendationCoverCacheService(Jable())
    assert missav.is_allowed_url("https://fourhoi.com/test-123/cover-t.jpg")
    assert not jable.is_allowed_url("https://fourhoi.com/test-123/cover-t.jpg")
    for url in (
        "http://localhost/a.jpg",
        "https://fourhoi.com.evil.test/a.jpg",
        "https://user@fourhoi.com/a.jpg",
        "https://fourhoi.com:8080/a.jpg",
    ):
        assert not missav.is_allowed_url(url)


def test_missav_cache_is_atomic_bounded_and_does_not_send_cookie(
    tmp_path, settings, monkeypatch
):
    settings.RECOMMENDATION_COVER_DIR = tmp_path
    source = MissAV("http://proxy.test:8080")
    source.cookie = "private=session"
    service = RecommendationCoverCacheService(source)
    response = Mock(status_code=200, headers={"Content-Type": "image/jpeg"})
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    response.iter_content.return_value = iter([b"image"])
    get = Mock(return_value=response)
    monkeypatch.setattr("nassav.recommendation.cover_cache.requests.get", get)
    url = "https://fourhoi.com/test-123/cover-t.jpg"
    path = service.ensure_cached(url)
    assert path.read_bytes() == b"image"
    assert "Cookie" not in get.call_args.kwargs["headers"]
    assert get.call_args.kwargs["allow_redirects"] is False
    assert service.ensure_cached(url) == path
    assert get.call_count == 1
    path.unlink()
    response.iter_content.return_value = iter([b"x" * (5 * 1024 * 1024 + 1)])
    assert service.ensure_cached(url) is None
    assert not list(tmp_path.iterdir())
