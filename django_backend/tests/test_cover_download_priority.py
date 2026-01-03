"""测试封面下载的优先级和回退逻辑"""
from unittest.mock import MagicMock, Mock, patch

import pytest


@pytest.mark.django_db
def test_cover_download_priority():
    """测试封面下载优先使用Javbus，失败时回退到Source"""
    from nassav.scraper.AVDownloadInfo import AVDownloadInfo
    from nassav.source.SourceManager import SourceManager

    # 创建模拟对象
    mock_source = Mock()
    mock_source.get_source_name.return_value = "TestSource"
    mock_source.get_cover_url.return_value = "https://source.com/cover.jpg"
    mock_source.download_file.return_value = True

    manager = SourceManager()

    # 模拟Javbus返回封面URL和scraper.download_cover
    with patch.object(manager.scraper, "scrape") as mock_scrape, patch.object(
        manager.scraper, "download_cover", return_value=True
    ) as mock_download:
        mock_scrape.return_value = {
            "title": "测试标题",
            "cover_url": "https://www.javbus.com/pics/cover/test.jpg",
            "actors": ["演员A"],
            "actor_avatars": {},
        }

        info = AVDownloadInfo(avid="TEST-001", m3u8="", source="test")
        html = "<html></html>"

        # 执行保存
        result = manager.save_all_resources("TEST-001", info, mock_source, html)

        # 验证使用了scraper.download_cover（Javbus封面）
        assert mock_download.called
        call_args = mock_download.call_args
        downloaded_url = call_args[0][0]
        assert "javbus.com" in downloaded_url
        # Source的download_file不应该被调用
        assert not mock_source.download_file.called


@pytest.mark.django_db
def test_cover_fallback_to_source():
    """测试Javbus无封面时回退到Source封面"""
    from nassav.scraper.AVDownloadInfo import AVDownloadInfo
    from nassav.source.SourceManager import SourceManager

    # 创建模拟对象
    mock_source = Mock()
    mock_source.get_source_name.return_value = "TestSource"
    mock_source.get_cover_url.return_value = "https://source.com/cover.jpg"
    mock_source.download_file.return_value = True

    manager = SourceManager()

    # 模拟Javbus返回数据但没有封面URL
    with patch.object(manager.scraper, "scrape") as mock_scrape:
        mock_scrape.return_value = {
            "title": "测试标题",
            "actors": ["演员A"],
            "actor_avatars": {}
            # 没有cover_url字段
        }

        info = AVDownloadInfo(avid="TEST-002", m3u8="", source="test")
        html = "<html></html>"

        # 执行保存
        result = manager.save_all_resources("TEST-002", info, mock_source, html)

        # 验证调用了Source的get_cover_url
        assert mock_source.get_cover_url.called
        # 验证使用了Source的封面
        assert mock_source.download_file.called
        call_args = mock_source.download_file.call_args
        downloaded_url = call_args[0][0]
        assert "source.com" in downloaded_url


@pytest.mark.django_db
def test_no_cover_available():
    """测试Javbus和Source都没有封面的情况"""
    from nassav.scraper.AVDownloadInfo import AVDownloadInfo
    from nassav.source.SourceManager import SourceManager

    # 创建模拟对象
    mock_source = Mock()
    mock_source.get_source_name.return_value = "TestSource"
    mock_source.get_cover_url.return_value = None  # Source也没有封面
    mock_source.download_file.return_value = True

    manager = SourceManager()

    # 模拟Javbus也没有封面
    with patch.object(manager.scraper, "scrape") as mock_scrape:
        mock_scrape.return_value = {
            "title": "测试标题",
            "actors": []
            # 没有cover_url
        }

        info = AVDownloadInfo(avid="TEST-003", m3u8="", source="test")
        html = "<html></html>"

        # 执行保存
        result = manager.save_all_resources("TEST-003", info, mock_source, html)

        # 验证cover_saved为False
        assert result["cover_saved"] is False
