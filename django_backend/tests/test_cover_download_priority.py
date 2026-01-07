"""测试封面下载的优先级和回退逻辑"""
from unittest.mock import MagicMock, Mock, patch

import pytest


@pytest.mark.django_db
def test_cover_download_priority():
    """测试封面下载优先使用Javbus，失败时回退到Source"""
    from nassav.resource_service import ResourceService
    from nassav.scraper import AVDownloadInfo
    from nassav.scraper.ScraperManager import scraper_manager
    from nassav.source.SourceManager import source_manager
    from nassav.translator.TranslatorManager import translator_manager

    # 创建模拟对象
    mock_source = Mock()
    mock_source.get_source_name.return_value = "TestSource"
    mock_source.get_cover_url.return_value = "https://source.com/cover.jpg"
    mock_source.download_file.return_value = True

    # 创建ResourceService实例
    service = ResourceService(source_manager, scraper_manager, translator_manager)

    # 模拟Javbus返回封面URL
    scraped_data = {
        "original_title": "测试标题",
        "cover_url": "https://www.javbus.com/pics/cover/test.jpg",
        "actors": [{"name": "演员A", "avatar_url": ""}],
        "genres": [],
        "release_date": "2024-01-01",
        "duration": 120,
    }

    # Mock scraper的download_cover方法
    with patch.object(
        scraper_manager, "download_cover", return_value=True
    ) as mock_download:
        info = AVDownloadInfo(
            avid="TEST-001", m3u8="", source_title="测试标题", source="test"
        )
        html = "<html></html>"

        # 测试_download_cover方法
        result = service._download_cover("TEST-001", scraped_data, mock_source, html)

        # 验证使用了scraper.download_cover（Javbus封面）
        assert mock_download.called
        call_args = mock_download.call_args
        downloaded_url = call_args[0][0]
        assert "javbus.com" in downloaded_url
        # Source的download_file不应该被调用
        assert not mock_source.download_file.called
        assert result is True


@pytest.mark.django_db
def test_cover_fallback_to_source():
    """测试Javbus无封面时回退到Source封面"""
    from nassav.resource_service import ResourceService
    from nassav.scraper import AVDownloadInfo
    from nassav.scraper.ScraperManager import scraper_manager
    from nassav.source.SourceManager import source_manager
    from nassav.translator.TranslatorManager import translator_manager

    # 创建模拟对象
    mock_source = Mock()
    mock_source.get_source_name.return_value = "TestSource"
    mock_source.get_cover_url.return_value = "https://source.com/cover.jpg"
    mock_source.download_file.return_value = True

    # 创建ResourceService实例
    service = ResourceService(source_manager, scraper_manager, translator_manager)

    # Javbus返回数据但没有封面URL
    scraped_data = {
        "original_title": "测试标题",
        "actors": [{"name": "演员A", "avatar_url": ""}],
        "genres": [],
        # 没有cover_url字段
    }

    info = AVDownloadInfo(avid="TEST-002", m3u8="", source_title="测试标题", source="test")
    html = "<html></html>"

    # 测试_download_cover方法
    result = service._download_cover("TEST-002", scraped_data, mock_source, html)

    # 验证调用了Source的get_cover_url
    assert mock_source.get_cover_url.called
    # 验证使用了Source的封面
    assert mock_source.download_file.called
    call_args = mock_source.download_file.call_args
    downloaded_url = call_args[0][0]
    assert "source.com" in downloaded_url
    assert result is True


@pytest.mark.django_db
def test_no_cover_available():
    """测试Javbus和Source都没有封面的情况"""
    from nassav.resource_service import ResourceService
    from nassav.scraper import AVDownloadInfo
    from nassav.scraper.ScraperManager import scraper_manager
    from nassav.source.SourceManager import source_manager
    from nassav.translator.TranslatorManager import translator_manager

    # 创建模拟对象
    mock_source = Mock()
    mock_source.get_source_name.return_value = "TestSource"
    mock_source.get_cover_url.return_value = None  # Source也没有封面
    mock_source.download_file.return_value = True

    # 创建ResourceService实例
    service = ResourceService(source_manager, scraper_manager, translator_manager)

    # Javbus也没有封面
    scraped_data = {
        "original_title": "测试标题",
        "actors": [],
        "genres": [],
        # 没有cover_url
    }

    info = AVDownloadInfo(avid="TEST-003", m3u8="", source_title="测试标题", source="test")
    html = "<html></html>"

    # 测试_download_cover方法
    result = service._download_cover("TEST-003", scraped_data, mock_source, html)

    # 验证cover_saved为False
    assert result is False
