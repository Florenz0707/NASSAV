#!/usr/bin/env python3
"""
翻译结果清理功能测试

功能：
1. 测试翻译结果中多余说明文字的清理
2. 验证各种格式的注释和说明文字能被正确移除
3. 确保标题内容被完整保留

测试用例：
- 包含"（注：...）"格式注释的标题
- 包含"翻译说明："及编号列表的标题
- 包含"标题："前缀的标题

运行方式：
    uv run tests/test_translation_cleaning.py

预期输出：
    显示每个测试用例的输入、期望输出、实际输出和通过状态

示例：
    $ uv run tests/test_translation_cleaning.py
    ================================================================================
    翻译结果清理测试
    ================================================================================

    测试用例: PRED-505
    --------------------------------------------------------------------------------
    输入:
    标题：因为被求婚的逢花是个"伪充真"的伪善者...

    期望输出:
    因为被求婚的逢花是个"伪充真"的伪善者...

    实际输出:
    因为被求婚的逢花是个"伪充真"的伪善者...

    ✅ 通过
    ================================================================================
"""

import sys
from pathlib import Path

# 设置路径
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

# 测试用例
test_cases = [
    {
        "name": "PRED-505",
        "input": """标题：因为被求婚的逢花是个"伪充真"的伪善者，真让人恼火，所以在婚礼前我想和她发生关系，让她多次为我怀孕。 山岸逢花

（注：翻译中保留了"伪充真"的概念，因为这是日本AV标题中常见的表达，用来形容那些表面上伪善但实际上行为不端的女性。同时，使用了"发生关系"和"怀孕"等直白的表达，以符合日本AV标题的风格。）""",
        "expected": '因为被求婚的逢花是个"伪充真"的伪善者，真让人恼火，所以在婚礼前我想和她发生关系，让她多次为我怀孕。 山岸逢花',
    },
    {
        "name": "ABF-139",
        "input": """标题：在一无所有的乡村里，和青梅竹马一起每天进行汗流浃背的激烈性爱。案例13：泷本雫葉【附带MGS专属的额外映像，时长30分钟】""",
        "expected": "在一无所有的乡村里，和青梅竹马一起每天进行汗流浃背的激烈性爱。案例13：泷本雫葉【附带MGS专属的额外映像，时长30分钟】",
    },
    {
        "name": "MIDV-023",
        "input": """Angel Kiss：ビアンたちの愛情物語8

翻译说明：
1. 保留了日语标题中的专有名词"ビアン（Bian）"，并将其翻译为"Bian（人名）"，并将其放在标题末尾。
2. 将标题翻译为"Angel Kiss：Bian们的爱情故事8"，保留了原标题中的"Angel Kiss"（天使之吻）这一浪漫元素，同时用"爱情故事"来传达标题中的浪漫情感。
3. 保留了原标题中的"8"（第8部），表示这是该系列中的第8部作品。
4. 采用了中文常见的AV作品标题表达方式，如"天使之吻"和"爱情故事"，同时保持了标题的简洁和吸引力。
5. 保持了原标题的中文表达风格，同时确保中文标题的流畅性和可读性。""",
        "expected": "Angel Kiss：ビアンたちの愛情物語8",
    },
    {
        "name": "带注释的简单标题",
        "input": """在无所事事的乡下与青梅竹马的浓密性爱生活 (注: 这是一个测试注释)""",
        "expected": "在无所事事的乡下与青梅竹马的浓密性爱生活",
    },
    {
        "name": "带中文括号注释",
        "input": """美少女的秘密恋情（注：保留了人名和地名）- 山田花子""",
        "expected": "美少女的秘密恋情- 山田花子",
    },
]


def test_cleaning():
    """测试清理函数"""
    from nassav.translator.OllamaTranslator import OllamaTranslator

    # 创建翻译器实例（仅用于测试清理功能）
    translator = OllamaTranslator()

    print("=" * 80)
    print("翻译结果清理测试")
    print("=" * 80)

    passed = 0
    failed = 0

    for test in test_cases:
        print(f"\n测试用例: {test['name']}")
        print("-" * 80)
        print("输入:")
        print(test["input"])
        print("\n期望输出:")
        print(test["expected"])

        # 执行清理
        cleaned = translator._clean_translation(test["input"])

        print("\n实际输出:")
        print(cleaned)

        # 验证
        if cleaned.strip() == test["expected"].strip():
            print("\n✅ 通过")
            passed += 1
        else:
            print("\n❌ 失败")
            print("差异:")
            print(f"  期望长度: {len(test['expected'].strip())}")
            print(f"  实际长度: {len(cleaned.strip())}")
            # 显示字符差异
            expected_lines = test["expected"].strip().split("\n")
            actual_lines = cleaned.strip().split("\n")
            if len(expected_lines) != len(actual_lines):
                print(
                    f"  行数不同: 期望 {len(expected_lines)} 行, 实际 {len(actual_lines)} 行"
                )
            failed += 1

        print("=" * 80)

    print(f"\n📊 测试完成: {passed} 通过, {failed} 失败")
    assert failed == 0, f"{failed} 个测试失败"


if __name__ == "__main__":
    import os

    import django

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "django_project.settings")
    django.setup()

    success = test_cleaning()
    sys.exit(0 if success else 1)
