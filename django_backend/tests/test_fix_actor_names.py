"""
测试 fix_actor_names 脚本的核心功能

功能：验证演员名称是否正常的判断逻辑

运行方法：
    uv run pytest tests/test_fix_actor_names.py -v
"""
import sys
from pathlib import Path

import pytest

# 导入脚本中的函数
script_path = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(script_path))

from fix_actor_names import is_actor_name_normal


@pytest.mark.parametrize(
    "name",
    [
        "めぐり（藤浦めぐ）",  # 完整的括号
        "ミュウ（夏目ミュウ、春川リサ、夏目衣織）",  # 完整的长括号
        "森沢かな（飯岡かなこ）",  # 完整的括号
        "明里つむぎ",  # 无括号
        "桥本有菜",  # 中文名
        "JULIA",  # 英文名
        "Test Actor (English Name)",  # 半角括号完整
    ],
)
def test_normal_names(name):
    """测试正常的演员名（不应该被标记为异常）"""
    assert is_actor_name_normal(name), f"'{name}' 应该被判断为正常，但被标记为异常"


@pytest.mark.parametrize(
    "name",
    [
        "めぐり（藤",  # 括号未闭合
        "ミュウ（夏",  # 括号未闭合
        "森沢かな（",  # 只有左括号
        "Test Actor (Incomplete",  # 半角括号未闭合
        "演员名（",  # 以未闭合括号结尾
    ],
)
def test_truncated_names(name):
    """测试被截断的演员名（应该被标记为异常）"""
    assert not is_actor_name_normal(name), f"'{name}' 应该被判断为异常（截断），但被标记为正常"


def test_empty_name():
    """测试空名称"""
    assert is_actor_name_normal("")
    assert is_actor_name_normal(None)


def test_multiple_parentheses():
    """测试多对括号的情况"""
    # 正常：括号成对
    assert is_actor_name_normal("演员（名字A）和（名字B）")
    assert is_actor_name_normal("Actor (Name A) and (Name B)")

    # 异常：括号不成对
    assert not is_actor_name_normal("演员（名字A）和（名字B")
    assert not is_actor_name_normal("Actor (Name A) and (Name B")


def test_mixed_parentheses():
    """测试混合全角半角括号"""
    # 正常：各自成对
    assert is_actor_name_normal("演员（全角）and (半角)")

    # 异常：全角不成对
    assert not is_actor_name_normal("演员（全角 and (半角)")

    # 异常：半角不成对
    assert not is_actor_name_normal("演员（全角）and (半角")


def test_nested_parentheses():
    """测试嵌套括号（虽然不常见）"""
    # 嵌套括号只要数量匹配就算正常
    assert is_actor_name_normal("演员（外层（内层））")

    # 嵌套括号数量不匹配
    assert not is_actor_name_normal("演员（外层（内层）")


def test_special_characters():
    """测试包含特殊字符的名称"""
    # 不包含括号的特殊字符应该都算正常
    assert is_actor_name_normal("明里つむぎ・桥本有菜")
    assert is_actor_name_normal("A-B-C")
    assert is_actor_name_normal("演员123")
    assert is_actor_name_normal("@#$%")


def test_ending_with_parenthesis():
    """测试以括号结尾的情况"""
    # 以未闭合括号结尾应该判断为异常
    assert not is_actor_name_normal("演员名（")

    # 以闭合括号结尾应该判断为正常
    assert is_actor_name_normal("演员名（完整）")


@pytest.mark.parametrize(
    "name",
    [
        "めぐり（藤",  # JUR-448
        "ミュウ（夏",  # MIDV-023
        "森沢かな（",  # 某个资源
    ],
)
def test_real_truncated_examples(name):
    """测试真实的截断案例"""
    assert not is_actor_name_normal(name), f"真实截断案例 '{name}' 应该被检测出来"


@pytest.mark.parametrize(
    "name",
    [
        "めぐり（藤浦めぐ）",
        "ミュウ（夏目ミュウ、春川リサ、夏目衣織）",
        "森沢かな（飯岡かなこ）",
        "明里つむぎ",
        "桥本有菜",
        "JULIA",
    ],
)
def test_real_normal_examples(name):
    """测试真实的正常案例"""
    assert is_actor_name_normal(name), f"真实正常案例 '{name}' 不应该被标记为异常"
