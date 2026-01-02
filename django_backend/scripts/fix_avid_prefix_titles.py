#!/usr/bin/env python
"""
修复以 AVID 开头的标题

功能：
    查找并修复标题以 AVID 开头的资源记录（这通常是刮削失败的标志）

处理流程：
    1. 查找所有 title 字段以 AVID 开头的资源
    2. 重新从 Javbus 刮削获取正确的标题
    3. 可选：使用 Ollama 翻译新标题

用法：
    # 预览模式（列出问题资源，不修改）
    uv run python scripts/fix_avid_prefix_titles.py --list-only

    # 预览模式（显示将要执行的操作）
    uv run python scripts/fix_avid_prefix_titles.py

    # 实际执行修复（不翻译）
    uv run python scripts/fix_avid_prefix_titles.py --execute --no-translate

    # 实际执行修复并翻译
    uv run python scripts/fix_avid_prefix_titles.py --execute

    # 自定义请求延迟
    uv run python scripts/fix_avid_prefix_titles.py --execute --delay 3.0

选项：
    --execute       实际执行修改（默认为预览模式）
    --list-only     仅列出问题资源，不进行处理
    --no-translate  不进行翻译
    --delay SECONDS 每次请求之间的延迟（默认 2 秒）

依赖：
    - Javbus scraper
    - Ollama (可选，用于翻译)

注意：
    - 默认为预览模式（dry-run），不会修改数据库
    - 只更新 title 字段（Scraper原文），不影响 source_title 和 translated_title
    - 建议先使用 --list-only 查看问题资源
"""

import argparse
import os
import re
import sys
import time
from pathlib import Path

# 设置 Django 环境
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "django_project.settings")

import django

django.setup()

from django.db.models import Q
from loguru import logger
from nassav.models import AVResource
from nassav.scraper import ScraperManager
from nassav.translator import translator_manager


def find_avid_prefix_resources():
    """查找所有标题以 AVID 开头的资源"""
    resources = (
        AVResource.objects.exclude(title__isnull=True)
        .exclude(title="")
        .exclude(translated_title__isnull=True)
        .exclude(translated_title="")
    )

    avid_prefix_resources = []
    for resource in resources:
        # 检查标题是否以 AVID 开头（忽略大小写）
        logger.info(f"检查 {resource.avid} - 标题: {resource.translated_title[:30]}...")
        if resource.title and resource.title.upper().startswith(resource.avid.upper()):
            avid_prefix_resources.append(resource)

    return avid_prefix_resources


def fix_titles(dry_run: bool = False, delay: float = 2.0, translate: bool = True):
    """修复以 AVID 开头的标题"""

    logger.info("=" * 60)
    logger.info("修复以 AVID 开头的标题")
    logger.info("=" * 60)

    # 查找问题资源
    resources = find_avid_prefix_resources()

    if not resources:
        logger.info("✓ 没有找到以 AVID 开头的标题")
        return

    logger.info(f"找到 {len(resources)} 个以 AVID 开头的标题:")
    for r in resources:
        logger.info(f"  - {r.avid}: {r.title[:60]}...")

    logger.info("-" * 60)

    if dry_run:
        logger.warning("⚠️  预览模式，不会实际修改数据")

    # 初始化刮削器
    from django.conf import settings

    proxy = settings.PROXY_URL if settings.PROXY_ENABLED else None
    scraper = ScraperManager(proxy)

    # 检查翻译器
    if translate:
        available_translators = translator_manager.get_available_translators()
        if available_translators:
            logger.info(f"✓ 翻译器可用: {available_translators}")
        else:
            logger.warning("⚠️  没有可用的翻译器，将跳过翻译")
            translate = False

    # 统计
    success_count = 0
    failed_count = 0
    skipped_count = 0
    translated_count = 0

    for idx, resource in enumerate(resources, 1):
        avid = resource.avid
        old_title = resource.title

        logger.info(f"\n[{idx}/{len(resources)}] 处理 {avid}")
        logger.info(f"  旧标题: {old_title[:60]}...")

        # 从 Javbus 重新刮削
        try:
            scraped_data = scraper.scrape(avid)

            if not scraped_data:
                logger.warning(f"  ✗ 刮削失败，跳过")
                failed_count += 1
                time.sleep(delay)
                continue

            new_title = scraped_data.get("title", "")

            if not new_title:
                logger.warning(f"  ✗ 刮削结果无标题，跳过")
                failed_count += 1
                time.sleep(delay)
                continue

            # 检查新标题是否还是以 AVID 开头
            if new_title.upper().startswith(avid.upper()):
                logger.warning(f"  ⚠️  新标题仍以 AVID 开头，尝试手动移除")
                # 手动移除 AVID 前缀
                new_title = re.sub(
                    rf"^{avid}\s*", "", new_title, flags=re.IGNORECASE
                ).strip()
                if not new_title:
                    logger.warning(f"  ✗ 移除 AVID 后标题为空，跳过")
                    failed_count += 1
                    time.sleep(delay)
                    continue

            logger.info(f"  新标题: {new_title[:60]}...")

            if old_title == new_title:
                logger.info(f"  ⚠️  标题未变化，跳过")
                skipped_count += 1
                time.sleep(delay)
                continue

            # 更新标题
            if not dry_run:
                resource.title = new_title
                resource.save(update_fields=["title"])
                logger.info(f"  ✓ 标题已更新")
            else:
                logger.info(f"  [预览] 将更新标题")

            success_count += 1

            # 翻译新标题
            if translate and new_title:
                logger.info(f"  正在翻译...")
                try:
                    translated = translator_manager.translate(new_title)
                    if translated:
                        logger.info(f"  译文: {translated[:60]}...")
                        if not dry_run:
                            resource.translated_title = translated
                            resource.save(update_fields=["translated_title"])
                            logger.info(f"  ✓ 翻译已保存")
                        else:
                            logger.info(f"  [预览] 将保存翻译")
                        translated_count += 1
                    else:
                        logger.warning(f"  ⚠️  翻译返回空结果")
                except Exception as e:
                    logger.error(f"  ✗ 翻译失败: {e}")

        except Exception as e:
            logger.error(f"  ✗ 处理失败: {e}")
            failed_count += 1

        # 延迟避免请求过快
        if idx < len(resources):
            time.sleep(delay)

    # 统计结果
    logger.info("\n" + "=" * 60)
    logger.info("处理完成统计")
    logger.info("=" * 60)
    logger.info(f"总记录数: {len(resources)}")
    logger.info(f"成功更新: {success_count}")
    logger.info(f"翻译成功: {translated_count}")
    logger.info(f"处理失败: {failed_count}")
    logger.info(f"跳过记录: {skipped_count}")

    if dry_run:
        logger.warning("\n⚠️  这是预览运行，没有实际修改数据")
        logger.info("使用 --execute 参数来实际执行修改")


def main():
    parser = argparse.ArgumentParser(description="修复以 AVID 开头的标题")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="实际执行修改（默认为预览模式）",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=2.0,
        help="请求延迟（秒，默认: 2.0）",
    )
    parser.add_argument(
        "--no-translate",
        action="store_true",
        help="不进行翻译",
    )
    parser.add_argument(
        "--list-only",
        action="store_true",
        help="仅列出问题资源，不进行处理",
    )

    args = parser.parse_args()

    if args.list_only:
        resources = find_avid_prefix_resources()
        if resources:
            logger.info(f"找到 {len(resources)} 个以 AVID 开头的标题:")
            for r in resources:
                logger.info(f"  {r.avid}: {r.title}")
        else:
            logger.info("✓ 没有找到以 AVID 开头的标题")
        return

    fix_titles(
        dry_run=not args.execute,
        delay=args.delay,
        translate=not args.no_translate,
    )


if __name__ == "__main__":
    main()
