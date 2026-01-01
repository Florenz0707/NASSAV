#!/usr/bin/env python
"""
TranslatorManager 测试脚本

功能：
1. 测试 TranslatorManager 初始化和翻译器注册
2. 测试单条翻译（使用轮询机制）
3. 测试批量翻译
4. 测试指定翻译器翻译
5. 测试失败重试和降级机制

使用方法：
    python scripts/test_translator_manager.py
"""

import sys
import os

# 添加项目根目录到 Python 路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# 设置 Django 环境
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'django_project.settings')

import django
django.setup()

from loguru import logger
from nassav.translator import TranslatorManager, translator_manager

# 配置日志
logger.remove()
logger.add(sys.stderr, level="INFO")


def test_manager_initialization():
    """测试 TranslatorManager 初始化"""
    print("\n" + "=" * 60)
    print("测试 1: TranslatorManager 初始化")
    print("=" * 60)

    manager = TranslatorManager()

    print(f"可用翻译器: {manager.get_available_translators()}")
    print(f"翻译器优先级: {manager.translator_priority}")
    print(f"是否有可用翻译器: {manager.is_available()}")

    if manager.is_available():
        print("✓ TranslatorManager 初始化成功")
        return True
    else:
        print("✗ 没有可用的翻译器")
        return False


def test_global_instance():
    """测试全局单例实例"""
    print("\n" + "=" * 60)
    print("测试 2: 全局单例实例")
    print("=" * 60)

    # 使用全局实例
    print(f"全局实例可用翻译器: {translator_manager.get_available_translators()}")
    print(f"全局实例是否可用: {translator_manager.is_available()}")

    # 测试两次获取是否是同一个实例
    from nassav.translator import get_translator_manager
    manager1 = get_translator_manager()
    manager2 = get_translator_manager()

    if manager1 is manager2:
        print("✓ 全局单例模式正常")
        return True
    else:
        print("✗ 单例模式异常")
        return False


def test_single_translation():
    """测试单条翻译（自动轮询）"""
    print("\n" + "=" * 60)
    print("测试 3: 单条翻译（自动轮询）")
    print("=" * 60)

    test_texts = [
        "新人NO.1STYLE 小宵こなんAVデビュー",
        "絶対領域 透明感のあるスリムな太ももで常に誘惑 小悪魔ニーハイ美少女 橋本ありな",
    ]

    for i, text in enumerate(test_texts, 1):
        print(f"\n[测试 {i}]")
        print(f"原文: {text}")

        result = translator_manager.translate(text)

        if result:
            print(f"译文: {result}")
            print("✓ 翻译成功")
        else:
            print("✗ 翻译失败")
            return False

    return True


def test_batch_translation():
    """测试批量翻译"""
    print("\n" + "=" * 60)
    print("测试 4: 批量翻译")
    print("=" * 60)

    test_texts = [
        "新人NO.1STYLE 小宵こなんAVデビュー",
        "絶対領域 透明感のあるスリムな太ももで常に誘惑 小悪魔ニーハイ美少女 橋本ありな",
        "出張先ホテルで美女上司2人とまさかの相部屋… ダブルJカップという神展開で朝まで爆乳に挟まれヌイてもヌイても終わらない最高の射精体験 鷲尾めい 神宮寺ナオ",
    ]

    print(f"批量翻译 {len(test_texts)} 条文本\n")

    results = translator_manager.batch_translate(test_texts)

    print("\n翻译结果：")
    success_count = 0
    for i, (orig, trans) in enumerate(zip(test_texts, results), 1):
        print(f"\n[{i}]")
        print(f"原文: {orig}")
        if trans:
            print(f"译文: {trans}")
            print("✓ 成功")
            success_count += 1
        else:
            print("✗ 失败")

    print(f"\n成功率: {success_count}/{len(test_texts)}")
    return success_count == len(test_texts)


def test_specific_translator():
    """测试指定翻译器翻译"""
    print("\n" + "=" * 60)
    print("测试 5: 指定翻译器翻译")
    print("=" * 60)

    available = translator_manager.get_available_translators()
    if not available:
        print("✗ 没有可用的翻译器")
        return False

    translator_name = available[0]
    test_text = "新人NO.1STYLE 小宵こなんAVデビュー"

    print(f"使用指定翻译器: {translator_name}")
    print(f"原文: {test_text}")

    result = translator_manager.translate_from_specific(test_text, translator_name)

    if result:
        print(f"译文: {result}")
        print("✓ 翻译成功")
        return True
    else:
        print("✗ 翻译失败")
        return False


def test_retry_mechanism():
    """测试重试机制"""
    print("\n" + "=" * 60)
    print("测试 6: 重试机制")
    print("=" * 60)

    test_text = "新人NO.1STYLE 小宵こなんAVデビュー"

    print(f"原文: {test_text}")
    print("测试最大重试次数: 2")

    result = translator_manager.translate(test_text, max_retries=2)

    if result:
        print(f"译文: {result}")
        print("✓ 重试机制正常")
        return True
    else:
        print("✗ 重试失败")
        return False


def main():
    """主测试函数"""
    print("\n" + "=" * 60)
    print("TranslatorManager 测试脚本")
    print("=" * 60)

    tests = [
        ("初始化", test_manager_initialization),
        ("全局单例", test_global_instance),
        ("单条翻译", test_single_translation),
        ("批量翻译", test_batch_translation),
        ("指定翻译器", test_specific_translator),
        ("重试机制", test_retry_mechanism),
    ]

    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            logger.error(f"测试 {test_name} 异常: {e}")
            results.append((test_name, False))

    # 汇总结果
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)

    for test_name, result in results:
        status = "✓ 通过" if result else "✗ 失败"
        print(f"{test_name}: {status}")

    success_count = sum(1 for _, r in results if r)
    total_count = len(results)

    print(f"\n总体: {success_count}/{total_count} 测试通过")

    if success_count == total_count:
        print("\n✓ 所有测试通过")
    else:
        print(f"\n⚠️  有 {total_count - success_count} 个测试失败")

    print("=" * 60)


if __name__ == '__main__':
    main()
