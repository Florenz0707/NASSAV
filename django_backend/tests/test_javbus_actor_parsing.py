"""
测试 Javbus 女优名解析

功能：验证女优名从 img title 属性正确提取，不会被截断

运行方法：
    uv run python manage.py test tests.test_javbus_actor_parsing
"""
import os
from pathlib import Path

from django.test import TestCase
from nassav.scraper.Javbus import Javbus


class JavbusActorParsingTestCase(TestCase):
    """测试 Javbus 女优名解析"""

    def setUp(self):
        """加载测试 HTML 文件"""
        # 读取保存的 JUR-448.html 文件
        html_path = Path(__file__).parent.parent / "JUR-448.html"
        if not html_path.exists():
            self.html_content = None
            self.skipTest("JUR-448.html 文件不存在")
        else:
            with open(html_path, "r", encoding="utf-8") as f:
                self.html_content = f.read()

        self.scraper = Javbus()

    def test_actor_name_not_truncated(self):
        """测试女优名不会被截断（完整提取括号内容）"""
        if not self.html_content:
            self.skipTest("HTML 内容未加载")

        result = self.scraper.parse_html(self.html_content, "JUR-448")

        # 验证解析成功
        self.assertIsNotNone(result)
        self.assertIn("actors", result)

        # 验证女优名列表不为空
        actors = result["actors"]
        self.assertGreater(len(actors), 0)

        # 验证女优名是完整的（包含完整的括号内容）
        # 正确: めぐり（藤浦めぐ）
        # 错误: めぐり（藤
        expected_actor = "めぐり（藤浦めぐ）"
        self.assertIn(expected_actor, actors)

        # 确保没有被截断的名字
        truncated_actor = "めぐり（藤"
        self.assertNotIn(truncated_actor, actors)

    def test_actor_name_with_parentheses(self):
        """测试带括号的女优名完整性"""
        if not self.html_content:
            self.skipTest("HTML 内容未加载")

        result = self.scraper.parse_html(self.html_content, "JUR-448")

        actors = result.get("actors", [])
        self.assertGreater(len(actors), 0)

        # 检查女优名中的括号是否成对出现
        for actor in actors:
            open_count = actor.count("（")
            close_count = actor.count("）")
            # 如果有左括号，必须有相同数量的右括号
            if open_count > 0:
                self.assertEqual(
                    open_count,
                    close_count,
                    f"女优名 '{actor}' 的括号不匹配",
                )

    def test_extract_from_img_title_attribute(self):
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

        result = self.scraper.parse_html(test_html, "TEST-001")

        actors = result.get("actors", [])
        self.assertEqual(len(actors), 2)

        # 验证提取的是完整名字（从 img title），而不是截断的名字（从 span）
        self.assertIn("めぐり（藤浦めぐ）", actors)
        self.assertIn("测试演员（完整名字）", actors)

        # 确保不包含截断的名字
        self.assertNotIn("めぐり（藤", actors)
        self.assertNotIn("测试演员（完", actors)

    def test_real_html_metadata_extraction(self):
        """测试真实 HTML 的完整元数据提取"""
        if not self.html_content:
            self.skipTest("HTML 内容未加载")

        result = self.scraper.parse_html(self.html_content, "JUR-448")

        # 验证基本信息
        self.assertEqual(result["avid"], "JUR-448")
        self.assertIsNotNone(result["title"])
        self.assertGreater(len(result["title"]), 0)

        # 验证发行日期
        self.assertIsNotNone(result["release_date"])
        self.assertRegex(result["release_date"], r"\d{4}-\d{2}-\d{2}")

        # 验证时长
        self.assertIsNotNone(result["duration"])

        # 验证类别
        self.assertIsInstance(result["genres"], list)
        self.assertGreater(len(result["genres"]), 0)

        # 验证女优名
        self.assertIsInstance(result["actors"], list)
        self.assertGreater(len(result["actors"]), 0)
        self.assertIn("めぐり（藤浦めぐ）", result["actors"])
