#!/usr/bin/env python
"""
标题字段迁移脚本（历史脚本）

警告：
    此脚本用于早期数据库结构迁移，已经不再需要。
    现在的标题结构：
    - title: Scraper 获取的原文标题（日语）
    - source_title: Source 获取的备用标题
    - translated_title: 翻译后的标题（中文）

原功能：
    1. 将现有 AVResource.title 数据迁移到 source_title
    2. 从 Scraper 批量获取规范的日语标题填充到 title 字段
    3. 为后续的翻译功能做准备

历史用法：
    python manage.py runscript migrate_titles_to_new_schema

    或者在 Django shell 中：
    from scripts.migrate_titles_to_new_schema import migrate_titles
    migrate_titles(dry_run=True)  # 先测试
    migrate_titles(dry_run=False)  # 正式执行

注意：
    - 新项目不需要执行此脚本
    - 仅保留作为历史参考
"""
import sys
import time
from typing import Optional
from django.db import transaction
from loguru import logger

# 配置日志
logger.remove()
logger.add(sys.stderr, level="INFO")


def migrate_titles(dry_run: bool = True, batch_size: int = 10):
    """
    迁移标题字段

    Args:
        dry_run: 是否为试运行模式（不真正保存到数据库）
        batch_size: 每批处理的资源数量
    """
    from nassav.models import AVResource
    from nassav.scraper.ScraperManager import ScraperManager

    # 初始化 ScraperManager
    scraper_manager = ScraperManager(proxy=None)

    logger.info("=" * 60)
    logger.info("标题字段迁移脚本")
    logger.info(f"模式: {'试运行（不保存）' if dry_run else '正式执行'}")
    logger.info("=" * 60)

    # 统计信息
    stats = {
        'total': 0,
        'migrated_to_source_title': 0,
        'scraped_success': 0,
        'scraped_failed': 0,
        'skipped': 0,
    }

    # 查询所有资源
    resources = AVResource.objects.all().order_by('created_at')
    stats['total'] = resources.count()

    logger.info(f"共找到 {stats['total']} 个资源需要处理")

    if stats['total'] == 0:
        logger.info("没有资源需要处理")
        return stats

    # 分批处理
    processed = 0

    for i in range(0, stats['total'], batch_size):
        batch = resources[i:i + batch_size]
        logger.info(f"\n处理批次 {i//batch_size + 1}/{(stats['total']-1)//batch_size + 1}")

        for resource in batch:
            processed += 1
            avid = resource.avid
            old_title = resource.title

            logger.info(f"\n[{processed}/{stats['total']}] 处理资源: {avid}")
            logger.info(f"  原标题: {old_title[:50]}..." if len(old_title) > 50 else f"  原标题: {old_title}")

            # Step 1: 迁移现有 title 到 source_title
            if old_title and not resource.source_title:
                if not dry_run:
                    resource.source_title = old_title
                logger.info(f"  ✓ 已迁移到 source_title")
                stats['migrated_to_source_title'] += 1
            elif resource.source_title:
                logger.info(f"  - source_title 已存在，跳过迁移")
                stats['skipped'] += 1
            else:
                logger.info(f"  - 原标题为空，跳过")
                stats['skipped'] += 1

            # Step 2: 从 Scraper 获取规范标题
            if not resource.title or resource.title == old_title:
                logger.info(f"  尝试从 Scraper 获取规范标题...")
                scraped_data = scraper_manager.scrape(avid)

                if scraped_data and scraped_data.get('title'):
                    new_title = scraped_data['title']
                    logger.info(f"  ✓ 获取成功: {new_title[:50]}..." if len(new_title) > 50 else f"  ✓ 获取成功: {new_title}")

                    if not dry_run:
                        resource.title = new_title

                    stats['scraped_success'] += 1
                else:
                    logger.warning(f"  ✗ 获取失败，保持原标题")
                    stats['scraped_failed'] += 1
            else:
                logger.info(f"  - title 字段已更新，跳过 Scraper")

            # 保存更改
            if not dry_run:
                try:
                    resource.save()
                    logger.info(f"  ✓ 已保存到数据库")
                except Exception as e:
                    logger.error(f"  ✗ 保存失败: {e}")

            # 避免请求过快
            time.sleep(0.5)

        logger.info(f"\n批次完成，等待 2 秒...")
        time.sleep(2)

    # 输出统计信息
    logger.info("\n" + "=" * 60)
    logger.info("迁移完成统计")
    logger.info("=" * 60)
    logger.info(f"总资源数: {stats['total']}")
    logger.info(f"已迁移到 source_title: {stats['migrated_to_source_title']}")
    logger.info(f"Scraper 获取成功: {stats['scraped_success']}")
    logger.info(f"Scraper 获取失败: {stats['scraped_failed']}")
    logger.info(f"跳过: {stats['skipped']}")
    logger.info("=" * 60)

    if dry_run:
        logger.warning("\n⚠️  这是试运行模式，没有真正保存到数据库")
        logger.info("如需正式执行，请设置 dry_run=False")
    else:
        logger.success("\n✓ 迁移已完成并保存到数据库")

    return stats


def run():
    """
    Django-extensions runscript 入口点
    """
    import sys

    # 检查命令行参数
    dry_run = '--execute' not in sys.argv

    if dry_run:
        print("\n⚠️  试运行模式（默认）")
        print("如需正式执行，请添加 --execute 参数")
        print("例如: python manage.py runscript migrate_titles_to_new_schema --execute\n")

    migrate_titles(dry_run=dry_run)


if __name__ == '__main__':
    # 直接运行脚本
    import django
    import os
    import sys

    # 添加项目根目录到 Python 路径
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, project_root)

    # 设置 Django 环境
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'django_project.settings')
    django.setup()

    # 解析命令行参数
    dry_run = '--execute' not in sys.argv

    if dry_run:
        print("\n⚠️  试运行模式（默认）")
        print("如需正式执行，请添加 --execute 参数\n")

    migrate_titles(dry_run=dry_run)
