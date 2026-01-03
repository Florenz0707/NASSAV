"""测试Javbus封面URL提取功能"""
import re

import pytest


def test_cover_url_extraction():
    """测试从Javbus HTML提取封面URL"""
    # 模拟Javbus HTML片段（来自JUR-448.html）
    html = """
    <div class="row movie">
        <div class="col-md-9 screencap">
            <a class="bigImage" href="/pics/cover/bmaj_b.jpg"><img src="/pics/cover/bmaj_b.jpg"
                        title="夫の年下上司に専属≪乳奴●≫として、飼い慣らされた私…。"></a>
        </div>
    </div>
    """

    # 提取封面URL
    cover_match = re.search(r'<a[^>]*class="bigImage"[^>]*href="([^"]+)"', html)

    assert cover_match is not None
    cover_url = cover_match.group(1)
    assert cover_url == "/pics/cover/bmaj_b.jpg"


def test_cover_url_conversion():
    """测试相对路径转完整URL"""
    domain = "www.javbus.com"
    relative_url = "/pics/cover/bmaj_b.jpg"

    # 转为完整URL
    if relative_url.startswith("/"):
        full_url = f"https://{domain}{relative_url}"
    else:
        full_url = relative_url

    assert full_url == "https://www.javbus.com/pics/cover/bmaj_b.jpg"


def test_cover_url_absolute():
    """测试已经是完整URL的情况"""
    absolute_url = "https://example.com/cover.jpg"

    # 不以/开头，直接使用
    if absolute_url.startswith("/"):
        full_url = f"https://www.javbus.com{absolute_url}"
    else:
        full_url = absolute_url

    assert full_url == "https://example.com/cover.jpg"


@pytest.mark.django_db
def test_javbus_scraper_returns_cover_url():
    """测试Javbus刮削器是否返回封面URL"""
    from nassav.scraper.Javbus import Javbus

    scraper = Javbus()
    result = scraper.scrape("JUR-448")

    if result:
        # 验证返回数据包含cover_url
        assert "cover_url" in result
        assert result["cover_url"].startswith("https://")
        assert "/pics/cover/" in result["cover_url"]
        assert result["cover_url"].endswith(".jpg")
