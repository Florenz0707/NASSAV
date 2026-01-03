"""
测试 Javbus 女优名解析

功能：验证女优名从 img title 属性正确提取，不会被截断

运行方法：
    uv run pytest tests/test_javbus_actor_parsing.py -v
"""
from pathlib import Path

import pytest
from nassav.scraper.Javbus import Javbus


@pytest.fixture
def javbus_html_content():
    """加载测试 HTML 文件"""
    html_path = Path(__file__).parent.parent / "JUR-448.html"
    if not html_path.exists():
        pytest.skip("JUR-448.html 文件不存在")
    with open(html_path, "r", encoding="utf-8") as f:
        return f.read()


@pytest.fixture
def javbus_scraper():
    """返回 Javbus 爬虫实例"""
    return Javbus()


def test_actor_name_not_truncated(javbus_html_content, javbus_scraper):
    """测试女优名不会被截断（完整提取括号内容）"""
    result = javbus_scraper.parse_html(javbus_html_content, "JUR-448")

    # 验证解析成功
    assert result is not None
    assert "actors" in result

    # 验证女优名列表不为空
    actors = result["actors"]
    assert len(actors) > 0

    # 验证女优名是完整的（包含完整的括号内容）
    # 正确: めぐり（藤浦めぐ）
    # 错误: めぐり（藤
    expected_actor = "めぐり（藤浦めぐ）"
    assert expected_actor in actors

    # 确保没有被截断的名字
    truncated_actor = "めぐり（藤"
    assert truncated_actor not in actors


def test_actor_name_with_parentheses(javbus_html_content, javbus_scraper):
    """测试带括号的女优名完整性"""
    result = javbus_scraper.parse_html(javbus_html_content, "JUR-448")

    actors = result.get("actors", [])
    assert len(actors) > 0

    # 检查女优名中的括号是否成对出现
    for actor in actors:
        open_count = actor.count("（")
        close_count = actor.count("）")
        # 如果有左括号，必须有相同数量的右括号
        if open_count > 0:
            assert open_count == close_count, f"女优名 '{actor}' 的括号不匹配"


def test_extract_from_img_title_attribute(javbus_scraper):
    """测试从 img 标签的 title 属性提取女优名"""
    # 构造测试 HTML 片段
    test_html = """
    <div id="avatar-waterfall">
        <a class="avatar-box" href="https://www.javbus.com/star/305">
            <div class="photo-frame">
                <img src="/pics/actress/305_a.jpg" title="めぐり（藤浦めぐ）">
            </div>
            <span>めぐり（藤</span>
        </a>
        <a class="avatar-box" href="https://www.javbus.com/star/123">
            <div class="photo-frame">
                <img src="/pics/actress/123_a.jpg" title="测试演员（完整名字）">
            </div>
            <span>测试演员（完</span>
        </a>
    </div>
    """

    result = javbus_scraper.parse_html(test_html, "TEST-001")

    actors = result.get("actors", [])
    assert len(actors) == 2

    # 验证提取的是完整名字（从 img title），而不是截断的名字（从 span）
    assert "めぐり（藤浦めぐ）" in actors
    assert "测试演员（完整名字）" in actors

    # 确保不包含截断的名字
    assert "めぐり（藤" not in actors
    assert "测试演员（完" not in actors


def test_real_html_metadata_extraction(javbus_html_content, javbus_scraper):
    """测试真实 HTML 的完整元数据提取"""
    result = javbus_scraper.parse_html(javbus_html_content, "JUR-448")

    # 验证基本信息
    assert result["avid"] == "JUR-448"
    assert result["title"] is not None
    assert len(result["title"]) > 0

    # 验证发行日期
    assert result["release_date"] is not None
    assert isinstance(result["release_date"], str)
    # 验证日期格式 YYYY-MM-DD
    import re

    assert re.match(r"\d{4}-\d{2}-\d{2}", result["release_date"])

    # 验证时长
    assert result["duration"] is not None

    # 验证类别
    assert isinstance(result["genres"], list)
    assert len(result["genres"]) > 0

    # 验证女优名
    assert isinstance(result["actors"], list)
    assert len(result["actors"]) > 0
    assert "めぐり（藤浦めぐ）" in result["actors"]
