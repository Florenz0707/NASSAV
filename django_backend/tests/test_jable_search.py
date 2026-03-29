import pytest

from nassav.source import Jable


def test_jable_parse_search_results_extracts_cards():
    html = """
    <div class="row gutter-20">
      <div class="col-6 col-sm-4 col-lg-3">
        <div class="video-img-box mb-e-20">
          <div class="img-box cover-md">
            <a href="https://jable.tv/videos/fsdss-717/">
              <img
                class="lazyload"
                src="https://assets-cdn.jable.tv/assets/images/placeholder-md.jpg"
                data-src="https://assets-cdn.jable.tv/contents/videos_screenshots/36000/36472/320x180/1.jpg"
              >
              <div class="absolute-bottom-right">
                <span class="label">2:00:15</span>
              </div>
            </a>
          </div>
          <div class="detail">
            <h6 class="title">
              <a href="https://jable.tv/videos/fsdss-717/">
                FSDSS-717 【附有中文字幕】香港人・絵麗奈【初ドラマ】広東語講師の胸チラ無自覚誘惑に耐え切れず僕たちは言葉の壁を越えた
              </a>
            </h6>
            <p class="sub-title">
              <svg class="mr-1" height="15" width="15"></svg>3 290 381
              <svg class="ml-3 mr-1" height="13" width="13"></svg>9370
            </p>
          </div>
        </div>
      </div>
      <div class="col-6 col-sm-4 col-lg-3">
        <div class="video-img-box mb-e-20">
          <div class="img-box cover-md">
            <a href="/videos/jufd-994-c/">
              <img src="https://assets-cdn.jable.tv/contents/videos_screenshots/0/11/320x180/1.jpg">
              <div class="absolute-bottom-right">
                <span class="label">2:27:02</span>
              </div>
            </a>
          </div>
          <div class="detail">
            <h6 class="title"><a href="/videos/jufd-994-c/">JUFD-994 絕對服從的女秘書本田岬</a></h6>
            <p class="sub-title">1 877 855 5321</p>
          </div>
        </div>
      </div>
    </div>
    """

    jable = Jable()
    results = jable._parse_search_results(html)

    assert len(results) == 2

    first = results[0]
    assert first["avid"] == "FSDSS-717"
    assert first["detail_url"] == "https://jable.tv/videos/fsdss-717/"
    assert (
        first["cover_url"]
        == "https://assets-cdn.jable.tv/contents/videos_screenshots/36000/36472/320x180/1.jpg"
    )
    assert first["metrics"]["views"] == 3290381
    assert first["metrics"]["likes"] == 9370
    assert first["metrics"]["duration"] == "2:00:15"

    second = results[1]
    assert second["avid"] == "JUFD-994"
    assert second["detail_url"] == "https://jable.tv/videos/jufd-994-c/"
    assert second["metrics"]["views"] == 1877855
    assert second["metrics"]["likes"] == 5321


def test_jable_search_uses_fetch_html(monkeypatch):
    jable = Jable()

    captured = {}

    def fake_fetch_html(url, referer=""):
        captured["url"] = url
        captured["referer"] = referer
        return """
        <div class="video-img-box mb-e-20">
          <div class="img-box cover-md">
            <a href="/videos/abc-123/">
              <img data-src="https://example.com/abc.jpg">
            </a>
          </div>
          <div class="detail">
            <h6 class="title"><a href="/videos/abc-123/">ABC-123 Demo</a></h6>
            <p class="sub-title">12 345 67</p>
          </div>
        </div>
        """

    monkeypatch.setattr(jable, "fetch_html", fake_fetch_html)

    results = jable.search("中文字幕")

    assert (
        captured["url"]
        == "https://jable.tv/search/%E4%B8%AD%E6%96%87%E5%AD%97%E5%B9%95/"
    )
    assert captured["referer"] == "https://jable.tv/"
    assert len(results) == 1
    assert results[0]["avid"] == "ABC-123"
    assert results[0]["metrics"]["views"] == 12345
    assert results[0]["metrics"]["likes"] == 67


def test_jable_search_uses_from_parameter_for_later_pages(monkeypatch):
    jable = Jable()

    captured = {}

    def fake_fetch_html(url, referer=""):
        captured["url"] = url
        captured["referer"] = referer
        return ""

    monkeypatch.setattr(jable, "fetch_html", fake_fetch_html)

    jable.search("中文字幕", page=3)

    assert (
        captured["url"]
        == "https://jable.tv/search/%E4%B8%AD%E6%96%87%E5%AD%97%E5%B9%95/?from=03"
    )
    assert captured["referer"] == "https://jable.tv/"


def test_jable_get_model_videos_uses_model_slug_async_url(monkeypatch):
    jable = Jable()

    captured = {}

    def fake_fetch_html(url, referer=""):
        captured["url"] = url
        captured["referer"] = referer
        return """
        <div class="video-img-box mb-e-20">
          <div class="img-box cover-md">
            <a href="/videos/abc-123/">
              <img data-src="https://example.com/abc.jpg">
            </a>
          </div>
          <div class="detail">
            <h6 class="title"><a href="/videos/abc-123/">ABC-123 Demo</a></h6>
            <p class="sub-title">12 345 67</p>
          </div>
        </div>
        """

    monkeypatch.setattr(jable, "fetch_html", fake_fetch_html)

    results = jable.get_model_videos("tsumugi-akari")

    assert (
        captured["url"]
        == "https://jable.tv/models/tsumugi-akari/?mode=async&function=get_block&block_id=list_videos_common_videos_list&sort_by=video_viewed"
    )
    assert captured["referer"] == "https://jable.tv/models/tsumugi-akari/"
    assert results[0]["avid"] == "ABC-123"
    assert results[0]["metrics"]["model_slug"] == "tsumugi-akari"


def test_jable_get_model_videos_uses_from_parameter_for_later_pages(monkeypatch):
    jable = Jable()

    captured = {}

    def fake_fetch_html(url, referer=""):
        captured["url"] = url
        captured["referer"] = referer
        return ""

    monkeypatch.setattr(jable, "fetch_html", fake_fetch_html)

    jable.get_model_videos("tsumugi-akari", page=3)

    assert (
        captured["url"]
        == "https://jable.tv/models/tsumugi-akari/?mode=async&function=get_block&block_id=list_videos_common_videos_list&sort_by=video_viewed&from=03"
    )
    assert captured["referer"] == "https://jable.tv/models/tsumugi-akari/"


def test_jable_discover_hot_items_uses_async_hot_board_urls(monkeypatch):
    jable = Jable()

    captured_urls = []

    def fake_fetch_html(url, referer=""):
        captured_urls.append((url, referer))
        if "sort_by=video_viewed_today" in url:
            return """
            <div class="video-img-box mb-e-20">
              <div class="img-box cover-md">
                <a href="/videos/abc-123/">
                  <img data-src="https://example.com/abc.jpg">
                </a>
              </div>
              <div class="detail">
                <h6 class="title"><a href="/videos/abc-123/">ABC-123 Demo</a></h6>
                <p class="sub-title">12 345 67</p>
              </div>
            </div>
            """
        if "sort_by=video_viewed_week" in url:
            return """
            <div class="video-img-box mb-e-20">
              <div class="img-box cover-md">
                <a href="/videos/def-456/">
                  <img data-src="https://example.com/def.jpg">
                </a>
              </div>
              <div class="detail">
                <h6 class="title"><a href="/videos/def-456/">DEF-456 Demo</a></h6>
                <p class="sub-title">8 765 43</p>
              </div>
            </div>
            """
        return ""

    monkeypatch.setattr(jable, "fetch_html", fake_fetch_html)

    results = jable.discover_hot_items()

    assert [item["avid"] for item in results] == ["ABC-123", "DEF-456"]
    assert captured_urls == [
        (
            "https://jable.tv/hot/?mode=async&function=get_block&block_id=list_videos_common_videos_list&sort_by=video_viewed_today",
            "https://jable.tv/hot/",
        ),
        (
            "https://jable.tv/hot/?mode=async&function=get_block&block_id=list_videos_common_videos_list&sort_by=video_viewed_week",
            "https://jable.tv/hot/",
        ),
        (
            "https://jable.tv/hot/?mode=async&function=get_block&block_id=list_videos_common_videos_list&sort_by=video_viewed_month",
            "https://jable.tv/hot/",
        ),
        (
            "https://jable.tv/hot/?mode=async&function=get_block&block_id=list_videos_common_videos_list&sort_by=video_viewed",
            "https://jable.tv/hot/",
        ),
    ]
    assert results[0]["metrics"]["discovery_sources"] == ["hot_board"]
    assert results[0]["metrics"]["hot_board_sort"] == "video_viewed_today"
    assert results[1]["metrics"]["hot_board_sort"] == "video_viewed_week"


def test_jable_discover_hot_items_uses_from_parameter_for_later_pages(monkeypatch):
    jable = Jable()

    captured_urls = []

    def fake_fetch_html(url, referer=""):
        captured_urls.append((url, referer))
        return ""

    monkeypatch.setattr(jable, "fetch_html", fake_fetch_html)

    jable.discover_hot_items(page=3)

    assert captured_urls == [
        (
            "https://jable.tv/hot/?mode=async&function=get_block&block_id=list_videos_common_videos_list&sort_by=video_viewed_today&from=03",
            "https://jable.tv/hot/",
        ),
        (
            "https://jable.tv/hot/?mode=async&function=get_block&block_id=list_videos_common_videos_list&sort_by=video_viewed_week&from=03",
            "https://jable.tv/hot/",
        ),
        (
            "https://jable.tv/hot/?mode=async&function=get_block&block_id=list_videos_common_videos_list&sort_by=video_viewed_month&from=03",
            "https://jable.tv/hot/",
        ),
        (
            "https://jable.tv/hot/?mode=async&function=get_block&block_id=list_videos_common_videos_list&sort_by=video_viewed&from=03",
            "https://jable.tv/hot/",
        ),
    ]


def test_jable_discover_latest_updates_uses_latest_updates_path(monkeypatch):
    jable = Jable()

    captured = {}

    def fake_fetch_html(url, referer=""):
        captured["url"] = url
        captured["referer"] = referer
        return """
        <div class="video-img-box mb-e-20">
          <div class="img-box cover-md">
            <a href="/videos/ghi-789/">
              <img data-src="https://example.com/ghi.jpg">
            </a>
          </div>
          <div class="detail">
            <h6 class="title"><a href="/videos/ghi-789/">GHI-789 Demo</a></h6>
            <p class="sub-title">9 999 88</p>
          </div>
        </div>
        """

    monkeypatch.setattr(jable, "fetch_html", fake_fetch_html)

    results = jable.discover_latest_updates()

    assert captured["url"] == "https://jable.tv/latest-updates/"
    assert captured["referer"] == "https://jable.tv/latest-updates/"
    assert results[0]["avid"] == "GHI-789"
    assert results[0]["metrics"]["discovery_sources"] == ["latest_updates"]


def test_jable_discover_latest_updates_uses_from_parameter_for_later_pages(
    monkeypatch,
):
    jable = Jable()

    captured = {}

    def fake_fetch_html(url, referer=""):
        captured["url"] = url
        captured["referer"] = referer
        return ""

    monkeypatch.setattr(jable, "fetch_html", fake_fetch_html)

    jable.discover_latest_updates(page=3)

    assert captured["url"] == "https://jable.tv/latest-updates/?from=03"
    assert captured["referer"] == "https://jable.tv/latest-updates/"


@pytest.mark.parametrize(
    ("title", "detail_url", "expected"),
    [
        (
            "JUFD-994 絕對服從的女秘書本田岬",
            "https://jable.tv/videos/jufd-994-c/",
            "JUFD-994",
        ),
        ("", "https://jable.tv/videos/fsdss-717/", "FSDSS-717"),
        ("IPZZ-815 Demo", "", "IPZZ-815"),
    ],
)
def test_jable_extract_avid(title, detail_url, expected):
    jable = Jable()
    assert jable._extract_avid(title=title, detail_url=detail_url) == expected
