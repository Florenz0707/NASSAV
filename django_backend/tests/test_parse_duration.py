"""测试duration解析功能"""
import pytest


@pytest.mark.django_db
def test_parse_duration_from_string():
    """测试从字符串解析duration"""
    from nassav.resource_service import ResourceService
    from nassav.scraper.ScraperManager import scraper_manager
    from nassav.source.SourceManager import source_manager
    from nassav.translator.TranslatorManager import translator_manager

    service = ResourceService(source_manager, scraper_manager, translator_manager)

    # 测试 "98分钟" 格式
    assert service._parse_duration("98分钟") == 98 * 60

    # 测试 "120分" 格式
    assert service._parse_duration("120分") == 120 * 60

    # 测试纯数字字符串
    assert service._parse_duration("7200") == 7200

    # 测试已经是整数
    assert service._parse_duration(7200) == 7200

    # 测试None
    assert service._parse_duration(None) == 0

    # 测试无效字符串
    assert service._parse_duration("invalid") == 0

    # 测试空字符串
    assert service._parse_duration("") == 0
