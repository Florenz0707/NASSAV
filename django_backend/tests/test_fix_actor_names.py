"""
测试 fix_actor_names 脚本的核心功能

功能：验证演员名称是否正常的判断逻辑

运行方法：
    uv run python manage.py test tests.test_fix_actor_names
"""
# 导入脚本中的函数（需要确保脚本路径正确）
import sys
from pathlib import Path

from django.test import TestCase

script_path = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(script_path))

from fix_actor_names import is_actor_name_normal


class FixActorNamesTestCase(TestCase):
    """测试演员名称正常性判断"""

    def test_normal_names(self):
        """测试正常的演员名（不应该被标记为异常）"""
        normal_names = [
            "めぐり（藤浦めぐ）",  # 完整的括号
            "ミュウ（夏目ミュウ、春川リサ、夏目衣織）",  # 完整的长括号
            "森沢かな（飯岡かなこ）",  # 完整的括号
            "明里つむぎ",  # 无括号
            "桥本有菜",  # 中文名
            "JULIA",  # 英文名
            "Test Actor (English Name)",  # 半角括号完整
        ]

        for name in normal_names:
            with self.subTest(name=name):
                self.assertTrue(
                    is_actor_name_normal(name),
                    f"'{name}' 应该被判断为正常，但被标记为异常",
                )

    def test_truncated_names(self):
        """测试被截断的演员名（应该被标记为异常）"""
        truncated_names = [
            "めぐり（藤",  # 括号未闭合
            "ミュウ（夏",  # 括号未闭合
            "森沢かな（",  # 只有左括号
            "Test Actor (Incomplete",  # 半角括号未闭合
            "演员名（",  # 以未闭合括号结尾
        ]

        for name in truncated_names:
            with self.subTest(name=name):
                self.assertFalse(
                    is_actor_name_normal(name),
                    f"'{name}' 应该被判断为异常（截断），但被标记为正常",
                )

    def test_empty_name(self):
        """测试空名称"""
        self.assertTrue(is_actor_name_normal(""))
        self.assertTrue(is_actor_name_normal(None))

    def test_multiple_parentheses(self):
        """测试多对括号的情况"""
        # 正常：括号成对
        self.assertTrue(is_actor_name_normal("演员（名字A）和（名字B）"))
        self.assertTrue(is_actor_name_normal("Actor (Name A) and (Name B)"))

        # 异常：括号不成对
        self.assertFalse(is_actor_name_normal("演员（名字A）和（名字B"))
        self.assertFalse(is_actor_name_normal("Actor (Name A) and (Name B"))

    def test_mixed_parentheses(self):
        """测试混合全角半角括号"""
        # 正常：各自成对
        self.assertTrue(is_actor_name_normal("演员（全角）and (半角)"))

        # 异常：全角不成对
        self.assertFalse(is_actor_name_normal("演员（全角 and (半角)"))

        # 异常：半角不成对
        self.assertFalse(is_actor_name_normal("演员（全角）and (半角"))

    def test_nested_parentheses(self):
        """测试嵌套括号（虽然不常见）"""
        # 嵌套括号只要数量匹配就算正常
        self.assertTrue(is_actor_name_normal("演员（外层（内层））"))

        # 嵌套括号数量不匹配
        self.assertFalse(is_actor_name_normal("演员（外层（内层）"))

    def test_special_characters(self):
        """测试包含特殊字符的名称"""
        # 不包含括号的特殊字符应该都算正常
        self.assertTrue(is_actor_name_normal("明里つむぎ・桥本有菜"))
        self.assertTrue(is_actor_name_normal("A-B-C"))
        self.assertTrue(is_actor_name_normal("演员123"))
        self.assertTrue(is_actor_name_normal("@#$%"))

    def test_ending_with_parenthesis(self):
        """测试以括号结尾的情况"""
        # 以未闭合括号结尾应该判断为异常
        self.assertFalse(is_actor_name_normal("演员名（"))

        # 以闭合括号结尾应该判断为正常
        self.assertTrue(is_actor_name_normal("演员名（完整）"))

    def test_real_truncated_examples(self):
        """测试真实的截断案例"""
        # 这些是从实际数据库中发现的截断名称
        real_truncated = [
            "めぐり（藤",  # JUR-448
            "ミュウ（夏",  # MIDV-023
            "森沢かな（",  # 某个资源
        ]

        for name in real_truncated:
            with self.subTest(name=name):
                self.assertFalse(
                    is_actor_name_normal(name),
                    f"真实截断案例 '{name}' 应该被检测出来",
                )

    def test_real_normal_examples(self):
        """测试真实的正常案例"""
        real_normal = [
            "めぐり（藤浦めぐ）",
            "ミュウ（夏目ミュウ、春川リサ、夏目衣織）",
            "森沢かな（飯岡かなこ）",
            "明里つむぎ",
            "桥本有菜",
            "JULIA",
        ]

        for name in real_normal:
            with self.subTest(name=name):
                self.assertTrue(
                    is_actor_name_normal(name),
                    f"真实正常案例 '{name}' 不应该被标记为异常",
                )
