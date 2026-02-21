"""测试duration解析功能"""
import pytest


def test_parse_duration_from_string():
    """测试从字符串解析duration"""
    from nassav.utils import parse_duration

    assert parse_duration("98分钟") == 98 * 60
    assert parse_duration("120分") == 120 * 60
    assert parse_duration("7200") == 7200
    assert parse_duration(7200) == 7200
    assert parse_duration(None) == 0
    assert parse_duration("invalid") == 0
    assert parse_duration("") == 0
