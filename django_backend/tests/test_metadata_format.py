"""测试metadata格式和title字段处理"""
from unittest.mock import Mock

import pytest


@pytest.mark.django_db
def test_metadata_format_with_scraper_data():
    """测试有刮削数据时的metadata格式"""
    from nassav.resource_service import ResourceService
    from nassav.scraper import AVDownloadInfo
    from nassav.scraper.ScraperManager import scraper_manager
    from nassav.source.SourceManager import source_manager
    from nassav.translator.TranslatorManager import translator_manager

    # 创建ResourceService实例
    service = ResourceService(source_manager, scraper_manager, translator_manager)

    # 创建模拟的source对象
    mock_source = Mock()
    mock_source.get_source_name.return_value = "TestSource"

    # 创建AVDownloadInfo对象
    info = AVDownloadInfo(
        avid="TEST-001",
        m3u8="https://example.com/test.m3u8",
        source_title="Test Title from Source",  # 不以AVID开头，使用source_title字段
        source="TestSource",
    )

    # 模拟从scraper获取的数据
    scraped_data = {
        "title": "テストタイトル",  # 日语标题，应该映射到original_title
        "release_date": "2024-01-01",
        "duration": "120分钟",
        "director": "テスト監督",
        "studio": "テストスタジオ",
        "label": "テストレーベル",
        "series": "テストシリーズ",
        "genres": ["ジャンル1", "ジャンル2"],
        "actors": ["演员A", "演员B"],
        "actor_avatars": {
            "演员A": "https://javbus.com/avatar1.jpg",
            "演员B": "https://javbus.com/avatar2.jpg",
        },
        "cover_url": "https://javbus.com/cover.jpg",
    }

    # 调用_save_to_database方法
    resource = service._save_to_database("TEST-001", info, mock_source, scraped_data)

    # 验证source_title规范化（应该以AVID开头）
    assert resource.source_title.startswith("TEST-001")

    # 验证original_title从scraper的"title"字段获取
    assert resource.original_title == "テストタイトル"

    # 验证release_date
    assert resource.release_date == "2024-01-01"

    # 验证duration转换（120分钟 = 7200秒）
    assert resource.duration == 7200

    # 验证metadata格式（应该包含完整的AVDownloadInfo字段）
    metadata = resource.metadata
    assert metadata is not None
    assert metadata["m3u8"] == "https://example.com/test.m3u8"
    assert metadata["avid"] == "TEST-001"
    assert metadata["source"] == "TestSource"
    assert metadata["title"] == "テストタイトル"  # 应该更新为scraper的title
    assert metadata["release_date"] == "2024-01-01"
    assert metadata["duration"] == "120分钟"  # AVDownloadInfo中保持原格式
    assert metadata["director"] == "テスト監督"
    assert metadata["studio"] == "テストスタジオ"
    assert metadata["label"] == "テストレーベル"
    assert metadata["series"] == "テストシリーズ"
    assert "ジャンル1" in metadata["genres"]
    assert "演员A" in metadata["actors"]
    assert metadata["actor_avatars"]["演员A"] == "https://javbus.com/avatar1.jpg"

    # 验证演员和类别关联
    assert resource.actors.count() == 2
    assert resource.genres.count() == 2


@pytest.mark.django_db
def test_metadata_format_without_scraper_data():
    """测试没有刮削数据时的metadata格式"""
    from nassav.resource_service import ResourceService
    from nassav.scraper import AVDownloadInfo
    from nassav.scraper.ScraperManager import scraper_manager
    from nassav.source.SourceManager import source_manager
    from nassav.translator.TranslatorManager import translator_manager

    # 创建ResourceService实例
    service = ResourceService(source_manager, scraper_manager, translator_manager)

    # 创建模拟的source对象
    mock_source = Mock()
    mock_source.get_source_name.return_value = "TestSource"

    # 创建AVDownloadInfo对象
    info = AVDownloadInfo(
        avid="TEST-002",
        m3u8="https://example.com/test2.m3u8",
        source_title="Test Title 2",  # 不以AVID开头
        source="TestSource",
    )

    # 没有刮削数据
    scraped_data = None

    # 调用_save_to_database方法
    resource = service._save_to_database("TEST-002", info, mock_source, scraped_data)

    # 验证source_title规范化（应该以AVID开头）
    assert resource.source_title.startswith("TEST-002")

    # 验证没有original_title（因为没有scraper数据）
    assert not resource.original_title

    # 验证metadata格式（应该包含基本source信息）
    metadata = resource.metadata
    assert metadata is not None
    assert metadata["m3u8"] == "https://example.com/test2.m3u8"
    assert metadata["avid"] == "TEST-002"
    assert metadata["source"] == "TestSource"
    assert metadata["source_title"].startswith("TEST-002")


@pytest.mark.django_db
def test_source_title_normalization():
    """测试source_title规范化逻辑"""
    from nassav.resource_service import ResourceService
    from nassav.scraper import AVDownloadInfo
    from nassav.scraper.ScraperManager import scraper_manager
    from nassav.source.SourceManager import source_manager
    from nassav.translator.TranslatorManager import translator_manager

    service = ResourceService(source_manager, scraper_manager, translator_manager)
    mock_source = Mock()
    mock_source.get_source_name.return_value = "TestSource"

    # 测试1: 标题不以AVID开头
    info1 = AVDownloadInfo(
        avid="TEST-003", m3u8="", source_title="Some Title", source="TestSource"
    )
    resource1 = service._save_to_database("TEST-003", info1, mock_source, None)
    assert resource1.source_title == "TEST-003 Some Title"

    # 测试2: 标题已经以AVID开头
    info2 = AVDownloadInfo(
        avid="TEST-004",
        m3u8="",
        source_title="TEST-004 Another Title",
        source="TestSource",
    )
    resource2 = service._save_to_database("TEST-004", info2, mock_source, None)
    assert resource2.source_title == "TEST-004 Another Title"

    # 测试3: 标题以小写AVID开头
    info3 = AVDownloadInfo(
        avid="TEST-005",
        m3u8="",
        source_title="test-005 lowercase title",
        source="TestSource",
    )
    resource3 = service._save_to_database("TEST-005", info3, mock_source, None)
    # normalize_source_title应该识别小写AVID，不重复添加
    assert resource3.source_title.startswith(
        "TEST-005"
    ) or resource3.source_title.startswith("test-005")
