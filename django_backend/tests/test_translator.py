#!/usr/bin/env python
"""
Ollama 翻译器测试脚本

功能：
1. 测试 Ollama 服务是否可用
2. 测试单条翻译效果
3. 测试批量翻译功能
4. 从数据库读取真实日语标题进行翻译测试

使用方法：
    python tests/test_translator.py [--batch] [--count N]

    或者在 Django shell 中：
    from tests.test_translator import test_translator
    test_translator()
"""

import argparse
import os
import sys
import time
from typing import List, Tuple

import django

# 添加项目根目录到 Python 路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# 设置 Django 环境
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "django_project.settings")
django.setup()

from loguru import logger
from nassav.models import AVResource
from nassav.translator import OllamaTranslator

# 配置日志
logger.remove()
logger.add(sys.stderr, level="INFO")


def test_service_availability():
    """测试 Ollama 服务可用性"""
    print("\n" + "=" * 60)
    print("测试 1: 检查 Ollama 服务可用性")
    print("=" * 60)

    translator = OllamaTranslator()
    is_available = translator.is_available()

    if is_available:
        print(f"✓ Ollama 服务可用")
        print(f"  URL: {translator.url}")
        print(f"  Model: {translator.model}")
        return True
    else:
        print(f"✗ Ollama 服务不可用")
        print(f"  请检查服务是否运行: {translator.url}")
        return False


def test_single_translation():
    """测试单条翻译"""
    print("\n" + "=" * 60)
    print("测试 2: 单条翻译测试")
    print("=" * 60)

    translator = OllamaTranslator()

    # 测试样例
    test_cases = [
        "新人NO.1STYLE 小宵こなんAVデビュー",
        "絶対領域 透明感のあるスリムな太ももで常に誘惑 小悪魔ニーハイ美少女 橋本ありな",
        "出張先ホテルで美女上司2人とまさかの相部屋… ダブルJカップという神展開で朝まで爆乳に挟まれヌイてもヌイても終わらない最高の射精体験 鷲尾めい 神宮寺ナオ",
    ]

    results = []
    for i, japanese_text in enumerate(test_cases, 1):
        print(f"\n[测试 {i}]")
        print(f"日语原文: {japanese_text}")

        start_time = time.time()
        translated = translator.translate(japanese_text)
        elapsed = time.time() - start_time

        if translated:
            print(f"中文翻译: {translated}")
            print(f"✓ 翻译成功（耗时 {elapsed:.2f}秒）")
            results.append((True, japanese_text, translated, elapsed))
        else:
            print(f"✗ 翻译失败")
            results.append((False, japanese_text, None, elapsed))

    # 统计
    success_count = sum(1 for r in results if r[0])
    print(f"\n翻译成功率: {success_count}/{len(test_cases)}")
    avg_time = sum(r[3] for r in results) / len(results)
    print(f"平均耗时: {avg_time:.2f}秒")

    return results


def test_batch_translation(count: int = 5):
    """测试批量翻译"""
    print("\n" + "=" * 60)
    print(f"测试 3: 批量翻译测试（{count} 条）")
    print("=" * 60)

    # 从数据库随机选取资源
    resources = (
        AVResource.objects.filter(title__isnull=False)
        .exclude(title="")
        .order_by("?")[:count]
    )

    if not resources:
        print("✗ 数据库中没有可用的标题数据")
        return []

    print(f"从数据库中随机选取 {len(resources)} 条日语标题\n")

    translator = OllamaTranslator()
    japanese_texts = [r.title for r in resources]

    # 显示原文
    for i, text in enumerate(japanese_texts, 1):
        print(f"[{i}] {text}")

    print(f"\n开始批量翻译...")
    start_time = time.time()

    translated_texts = translator.batch_translate(japanese_texts)

    elapsed = time.time() - start_time

    # 显示结果
    print(f"\n翻译结果：")
    results = []
    for i, (orig, trans) in enumerate(zip(japanese_texts, translated_texts), 1):
        print(f"\n[{i}]")
        print(f"  日语: {orig}")
        if trans:
            print(f"  中文: {trans}")
            print(f"  ✓ 成功")
            results.append((True, orig, trans))
        else:
            print(f"  ✗ 失败")
            results.append((False, orig, None))

    # 统计
    success_count = sum(1 for r in results if r[0])
    print(f"\n" + "=" * 60)
    print(f"批量翻译完成")
    print(f"成功: {success_count}/{len(japanese_texts)}")
    print(f"总耗时: {elapsed:.2f}秒")
    print(f"平均每条: {elapsed/len(japanese_texts):.2f}秒")
    print("=" * 60)

    return results


def test_retry_mechanism():
    """测试重试机制"""
    print("\n" + "=" * 60)
    print("测试 4: 重试机制测试")
    print("=" * 60)

    translator = OllamaTranslator()

    # 使用一个正常的日语文本
    test_text = "新人NO.1STYLE 小宵こなんAVデビュー"

    print(f"原文: {test_text}")
    print(f"最大重试次数: {translator.max_retries}")

    start_time = time.time()
    result = translator.translate_with_retry(
        test_text, max_retries=translator.max_retries
    )
    elapsed = time.time() - start_time

    if result:
        print(f"✓ 翻译成功: {result}")
        print(f"  耗时: {elapsed:.2f}秒")
        return True
    else:
        print(f"✗ 翻译失败")
        return False


def test_database_samples(count: int = 10):
    """测试数据库中的真实样本"""
    print("\n" + "=" * 60)
    print(f"测试 5: 数据库真实样本测试（{count} 条）")
    print("=" * 60)

    # 选取既有 title（日语）又有 source_title（中文）的资源进行对比
    resources = (
        AVResource.objects.filter(title__isnull=False, source_title__isnull=False)
        .exclude(title="")
        .exclude(source_title="")
        .order_by("?")[:count]
    )

    if not resources:
        print("✗ 数据库中没有同时包含 title 和 source_title 的数据")
        return []

    translator = OllamaTranslator()

    print(f"选取 {len(resources)} 条资源进行对比测试\n")

    results = []
    for i, resource in enumerate(resources, 1):
        print(f"\n[{i}] {resource.avid}")
        print(f"  日语原文 (title):        {resource.title}")
        print(f"  中文原标题 (source_title): {resource.source_title}")

        start_time = time.time()
        translated = translator.translate(resource.title)
        elapsed = time.time() - start_time

        if translated:
            print(f"  AI翻译 (translated):      {translated}")
            print(f"  ✓ 翻译成功（耗时 {elapsed:.2f}秒）")
            results.append(
                {
                    "avid": resource.avid,
                    "title": resource.title,
                    "source_title": resource.source_title,
                    "translated": translated,
                    "success": True,
                    "time": elapsed,
                }
            )
        else:
            print(f"  ✗ 翻译失败")
            results.append(
                {
                    "avid": resource.avid,
                    "title": resource.title,
                    "source_title": resource.source_title,
                    "translated": None,
                    "success": False,
                    "time": elapsed,
                }
            )

        # 避免请求过快
        if i < len(resources):
            time.sleep(0.5)

    # 统计
    success_count = sum(1 for r in results if r["success"])
    avg_time = sum(r["time"] for r in results) / len(results)

    print(f"\n" + "=" * 60)
    print(f"数据库样本测试完成")
    print(f"成功率: {success_count}/{len(results)}")
    print(f"平均耗时: {avg_time:.2f}秒")
    print("=" * 60)

    return results


def main():
    """主测试函数"""
    parser = argparse.ArgumentParser(description="测试 Ollama 翻译器")
    parser.add_argument("--batch", action="store_true", help="运行批量翻译测试")
    parser.add_argument("--count", type=int, default=5, help="批量翻译测试的数量")
    parser.add_argument("--db-samples", action="store_true", help="测试数据库真实样本")
    parser.add_argument("--all", action="store_true", help="运行所有测试")

    args = parser.parse_args()

    print("\n" + "=" * 60)
    print("Ollama 翻译器测试脚本")
    print("=" * 60)

    # 测试 1: 服务可用性
    if not test_service_availability():
        print("\n⚠️  Ollama 服务不可用，无法继续测试")
        print("请确保 Ollama 已启动并加载了模型")
        return

    # 测试 2: 单条翻译
    test_single_translation()

    # 测试 4: 重试机制
    test_retry_mechanism()

    # 测试 3: 批量翻译（可选）
    if args.batch or args.all:
        test_batch_translation(args.count)

    # 测试 5: 数据库样本（可选）
    if args.db_samples or args.all:
        test_database_samples(args.count)

    print("\n" + "=" * 60)
    print("✓ 测试完成")
    print("=" * 60)


if __name__ == "__main__":
    main()
