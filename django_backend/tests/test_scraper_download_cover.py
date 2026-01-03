"""测试Scraper封面下载功能（带Referer头）"""
from unittest.mock import MagicMock, Mock, patch

import pytest


def test_scraper_download_cover_with_referer():
    """测试ScraperBase.download_cover是否设置了Referer头"""
    from nassav.scraper.Javbus import Javbus

    scraper = Javbus()
    scraper.domain = "www.javbus.com"

    # Mock requests.get
    with patch("nassav.scraper.ScraperBase.requests.get") as mock_get:
        mock_response = Mock()
        mock_response.iter_content.return_value = [b"fake image data"]
        mock_get.return_value = mock_response

        # 尝试下载封面
        url = "https://www.javbus.com/pics/cover/test.jpg"
        save_path = "/tmp/test.jpg"

        with patch("builtins.open", create=True) as mock_open:
            with patch("os.makedirs"):
                scraper.download_cover(url, save_path)

        # 验证requests.get被调用，且headers包含Referer
        assert mock_get.called
        call_kwargs = mock_get.call_args[1]
        headers = call_kwargs.get("headers", {})

        # 验证Referer头存在且正确
        assert "Referer" in headers
        assert headers["Referer"] == "https://www.javbus.com/"


def test_scraper_manager_download_cover():
    """测试ScraperManager.download_cover委托给scraper"""
    from unittest.mock import Mock

    from nassav.scraper.ScraperManager import ScraperManager

    manager = ScraperManager()

    # 创建一个mock scraper
    mock_scraper = Mock()
    mock_scraper.download_cover.return_value = True

    # 设置last_successful_scraper
    manager._last_successful_scraper = mock_scraper

    # 调用download_cover
    result = manager.download_cover("https://test.com/cover.jpg", "/tmp/test.jpg")

    # 验证委托给scraper
    assert result is True
    assert mock_scraper.download_cover.called
    call_args = mock_scraper.download_cover.call_args
    assert call_args[0][0] == "https://test.com/cover.jpg"
    assert call_args[0][1] == "/tmp/test.jpg"


def test_scraper_download_cover_error_handling():
    """测试封面下载失败时的错误处理"""
    from nassav.scraper.Javbus import Javbus

    scraper = Javbus()
    scraper.domain = "www.javbus.com"

    # Mock requests.get抛出异常
    with patch("nassav.scraper.ScraperBase.requests.get") as mock_get:
        mock_get.side_effect = Exception("Network error")

        # 尝试下载封面
        url = "https://www.javbus.com/pics/cover/test.jpg"
        save_path = "/tmp/test.jpg"

        result = scraper.download_cover(url, save_path)

        # 验证返回False
        assert result is False
