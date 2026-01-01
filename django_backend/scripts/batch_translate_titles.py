#!/usr/bin/env python
"""批量翻译现有资源的标题"""

import os
import sys
import django
from pathlib import Path

# 设置 Django 环境
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "django_project.settings")
django.setup()

from django.db.models import Q
from nassav.models import AVResource
from nassav.translator import translator_manager
from loguru import logger
import time


def batch_translate_titles(
    batch_size: int = 10,
    skip_existing: bool = True,
    test_mode: bool = False,
    test_limit: int = 5,
):
    """
    批量翻译资源标题

    Args:
        batch_size: 每批翻译的数量
        skip_existing: 是否跳过已有译文的记录
        test_mode: 测试模式，只翻译少量记录
        test_limit: 测试模式下的翻译数量限制
    """
    logger.info("=" * 60)
    logger.info("批量翻译标题脚本")
    logger.info("=" * 60)

    # 检查 TranslatorManager 是否可用
    available_translators = translator_manager.get_available_translators()
    if not available_translators:
        logger.error("❌ 没有可用的翻译器，请检查配置")
        return

    logger.info(f"✓ 翻译器可用: {available_translators}")

    # 构建查询条件
    if skip_existing:
        # 只翻译没有 translated_title 的记录
        query = Q(translated_title__isnull=True) | Q(translated_title="")
        query_desc = "需要翻译的"
    else:
        # 翻译所有记录
        query = Q()
        query_desc = "所有"

    # 只翻译有 title 的记录
    query &= Q(title__isnull=False) & ~Q(title="")

    # 统计数据
    total_count = AVResource.objects.filter(query).count()

    if total_count == 0:
        logger.info("✓ 没有需要翻译的记录")
        return

    logger.info(f"找到 {query_desc} {total_count} 条记录")

    # 测试模式限制
    if test_mode:
        actual_count = min(total_count, test_limit)
        logger.warning(f"⚠️  测试模式：只翻译前 {actual_count} 条记录")
    else:
        actual_count = total_count
        logger.info(f"开始批量翻译 {actual_count} 条记录（批次大小: {batch_size}）")

    # 获取需要翻译的记录
    resources = AVResource.objects.filter(query).order_by("id")
    if test_mode:
        resources = resources[:test_limit]

    # 分批处理
    success_count = 0
    failed_count = 0
    skipped_count = 0

    total_batches = (actual_count + batch_size - 1) // batch_size

    for batch_index in range(0, actual_count, batch_size):
        batch_num = batch_index // batch_size + 1
        batch = list(resources[batch_index : batch_index + batch_size])

        logger.info("-" * 60)
        logger.info(f"批次 {batch_num}/{total_batches} (记录 {batch_index + 1}-{min(batch_index + batch_size, actual_count)})")

        # 准备批量翻译的文本
        texts_to_translate = []
        resource_map = {}  # 索引 -> resource 映射

        for resource in batch:
            if not resource.title or resource.title.strip() == "":
                skipped_count += 1
                logger.warning(f"  [跳过] AVID={resource.avid}: 标题为空")
                continue

            texts_to_translate.append(resource.title)
            resource_map[len(texts_to_translate) - 1] = resource

        if not texts_to_translate:
            logger.info("  本批次无有效记录")
            continue

        # 批量翻译
        logger.info(f"  翻译 {len(texts_to_translate)} 条标题...")
        start_time = time.time()

        try:
            results = translator_manager.batch_translate(texts_to_translate)
            elapsed = time.time() - start_time

            logger.info(f"  翻译完成，耗时 {elapsed:.2f}s (平均 {elapsed/len(texts_to_translate):.2f}s/条)")

            # 保存结果
            for idx, translation in enumerate(results):
                resource = resource_map[idx]
                text = texts_to_translate[idx]

                if translation:
                    resource.translated_title = translation
                    resource.save(update_fields=["translated_title"])
                    success_count += 1
                    logger.info(f"  ✓ [成功] AVID={resource.avid}")
                    logger.debug(f"      原文: {text[:50]}...")
                    logger.debug(f"      译文: {translation[:50]}...")
                else:
                    failed_count += 1
                    logger.error(f"  ✗ [失败] AVID={resource.avid}: 翻译返回空结果")
                    logger.debug(f"      原文: {text[:50]}...")

        except Exception as e:
            logger.error(f"  ✗ 批次翻译失败: {e}")
            failed_count += len(texts_to_translate)
            continue

        # 短暂休息，避免过载
        if batch_num < total_batches:
            time.sleep(0.5)

    # 统计结果
    logger.info("=" * 60)
    logger.info("翻译完成统计")
    logger.info("=" * 60)
    logger.info(f"总记录数: {actual_count}")
    logger.info(f"成功翻译: {success_count} ({success_count/actual_count*100:.1f}%)")
    logger.info(f"翻译失败: {failed_count} ({failed_count/actual_count*100:.1f}%)")
    logger.info(f"跳过记录: {skipped_count}")

    if test_mode:
        logger.warning("⚠️  这是测试运行，只处理了部分记录")
        logger.info(f"完整运行需要处理 {total_count} 条记录")


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="批量翻译资源标题")
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="每批翻译的数量 (默认: 10)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="强制重新翻译已有译文的记录",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="测试模式，只翻译少量记录",
    )
    parser.add_argument(
        "--test-limit",
        type=int,
        default=5,
        help="测试模式下的翻译数量限制 (默认: 5)",
    )

    args = parser.parse_args()

    batch_translate_titles(
        batch_size=args.batch_size,
        skip_existing=not args.force,
        test_mode=args.test,
        test_limit=args.test_limit,
    )


if __name__ == "__main__":
    main()
