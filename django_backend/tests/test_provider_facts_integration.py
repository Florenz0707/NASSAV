from datetime import timedelta
from unittest.mock import Mock

import pytest
from django.utils import timezone
from nassav.composition import build_provider_facts_cache
from nassav.source.Jable import Jable
from nassav.models import ResourceMetadataCache, ResourcePlaybackCache

pytestmark = pytest.mark.django_db
HTML = """<title>TEST-001 Test title - Jable.TV</title><script>var hlsUrl = 'https://cdn.example/video.m3u8'</script><meta property="og:image" content="https://assets-cdn.jable.tv/cover.jpg"><section class="video-info"><div class="models"><a class="model" href="https://jable.tv/models/actor/" title="Actor">A</a></div><a href="/tags/genre/">Genre</a></section>"""


def source():
    item = Jable(facts_cache=build_provider_facts_cache())
    item.get_html = Mock(return_value=HTML)
    return item


def test_recommendation_reuses_durable_detail_without_network_and_captures_playback():
    item = source()
    detail = item.get_video_detail("TEST-001")
    assert detail["actors"] == ["Actor"]
    assert not detail["_provider_cache_hit"]
    item.get_html.assert_called_once()
    assert item.get_video_detail("TEST-001")["_provider_cache_hit"]
    assert item.get_html.call_count == 1
    assert (
        ResourceMetadataCache.objects.count()
        == ResourcePlaybackCache.objects.count()
        == 1
    )
    assert "m3u8" not in str(ResourceMetadataCache.objects.get().payload)
    assert item.cached_video_details([("TEST-001", item.get_detail_url("TEST-001"))])[
        "TEST-001"
    ]["genres"] == ["Genre"]


def test_force_refresh_expiry_and_wrong_identity_do_not_bless_bad_details():
    item = source()
    item.get_video_detail("TEST-001")
    item.get_video_detail("TEST-001", force_refresh=True)
    assert item.get_html.call_count == 2
    ResourceMetadataCache.objects.update(
        fresh_until=timezone.now() - timedelta(seconds=1)
    )
    assert item.cached_video_details([("TEST-001", "")]) == {}
    item.get_html.return_value = HTML.replace("TEST-001", "OTHER-001")
    with pytest.raises(ValueError, match="identity"):
        item.get_video_detail("TEST-001")
    assert ResourceMetadataCache.objects.get().payload["detail"]["avid"] == "TEST-001"
