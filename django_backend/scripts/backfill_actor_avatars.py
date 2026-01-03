#!/usr/bin/env python3
"""
迁移脚本：为现有演员批量获取头像

功能：
1. 查找所有没有头像的演员
2. 从关联的作品中获取AVID
3. 重新刮削Javbus获取头像URL
4. 下载并保存头像图片

使用方法：
    uv run python scripts/backfill_actor_avatars.py [--limit N] [--delay SECONDS] [--dry-run]

选项：
    --limit N       限制处理的演员数量（用于测试）
    --delay SECONDS 每次刮削之间的延迟（默认1秒，避免过于频繁请求）
    --dry-run       仅模拟运行，不实际更新数据库或下载文件
    --verbose       显示详细日志
"""

import argparse

# 配置Django环境
import os
import sys
import time
from pathlib import Path

import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "django_project.settings")
django.setup()

from django.conf import settings
from django.db.models import Count
from loguru import logger
from nassav import utils as nassav_utils
from nassav.models import Actor
from nassav.scraper.Javbus import Javbus


def backfill_avatars(limit=None, delay=1.0, dry_run=False, verbose=False):
    """为现有演员批量获取头像"""

    # 配置日志级别
    if not verbose:
        logger.remove()
        logger.add(sys.stderr, level="INFO")

    logger.info("=" * 60)
    logger.info("为现有演员批量获取头像")
    logger.info("=" * 60)

    # 1. 查找没有头像的演员（且有作品）
    actors_without_avatar = (
        Actor.objects.filter(avatar_url__isnull=True)
        .annotate(resource_count=Count("resources"))
        .filter(resource_count__gt=0)
        .order_by("-resource_count")
    )  # 按作品数倒序（优先处理热门演员）

    total_actors = actors_without_avatar.count()
    logger.info(f"找到 {total_actors} 个没有头像的演员")

    if limit:
        actors_without_avatar = actors_without_avatar[:limit]
        logger.info(f"限制处理数量为 {limit}")

    if dry_run:
        logger.warning("【DRY RUN 模式】不会实际修改数据库或下载文件")

    # 2. 初始化刮削器
    scraper = Javbus()

    # 统计
    stats = {
        "processed": 0,
        "success": 0,
        "failed": 0,
        "downloaded": 0,
        "skipped": 0,  # 未找到作品或刮削失败
    }

    # 3. 处理每个演员
    for actor in actors_without_avatar:
        stats["processed"] += 1
        logger.info(
            f"\n[{stats['processed']}/{len(actors_without_avatar)}] 处理演员: {actor.name} (作品数: {actor.resource_count})"
        )

        # 获取该演员的第一个作品AVID
        first_resource = actor.resources.first()
        if not first_resource:
            logger.warning(f"  跳过: 演员 {actor.name} 没有关联作品")
            stats["skipped"] += 1
            continue

        avid = first_resource.avid
        logger.info(f"  使用作品 {avid} 进行刮削")

        # 刮削作品元数据
        try:
            scrape_data = scraper.scrape(avid)
        except Exception as e:
            logger.error(f"  刮削失败: {e}")
            stats["failed"] += 1
            time.sleep(delay)
            continue

        if not scrape_data:
            logger.warning(f"  刮削失败: 未获取到元数据")
            stats["skipped"] += 1
            time.sleep(delay)
            continue

        # 检查是否有头像URL
        actor_avatars = scrape_data.get("actor_avatars", {})
        if actor.name not in actor_avatars:
            logger.warning(f"  跳过: 刮削结果中没有该演员的头像URL")
            stats["skipped"] += 1
            time.sleep(delay)
            continue

        avatar_url = actor_avatars[actor.name]
        logger.info(f"  找到头像URL: {avatar_url}")

        # 更新数据库
        if not dry_run:
            filename = avatar_url.rstrip("/").split("/")[-1]
            actor.avatar_url = avatar_url
            actor.avatar_filename = filename
            actor.save()
            logger.info(f"  ✓ 已更新数据库: {filename}")

            # 下载头像
            avatar_path = Path(settings.AVATAR_DIR) / filename
            if avatar_path.exists():
                logger.info(f"  头像已存在: {filename}")
            else:
                if nassav_utils.download_avatar(avatar_url, avatar_path):
                    stats["downloaded"] += 1
                    logger.info(f"  ✓ 下载成功: {filename}")
                else:
                    logger.warning(f"  ✗ 下载失败: {filename}")

            stats["success"] += 1
        else:
            logger.info(f"  [DRY RUN] 将更新: avatar_url={avatar_url}")
            stats["success"] += 1

        # 延迟（避免频繁请求）
        if delay > 0 and stats["processed"] < len(actors_without_avatar):
            time.sleep(delay)

    # 4. 输出统计信息
    logger.info("\n" + "=" * 60)
    logger.info("处理完成！")
    logger.info("=" * 60)
    logger.info(f"总演员数:   {stats['processed']}")
    logger.info(f"成功获取:   {stats['success']}")
    logger.info(f"下载头像:   {stats['downloaded']}")
    logger.info(f"跳过:       {stats['skipped']}")
    logger.info(f"失败:       {stats['failed']}")

    if not dry_run:
        # 显示AVATAR_DIR统计
        avatar_dir = Path(settings.AVATAR_DIR)
        avatar_files = list(avatar_dir.glob("*.jpg"))
        logger.info(f"\nAVATAR_DIR 文件总数: {len(avatar_files)}")


def main():
    parser = argparse.ArgumentParser(
        description="为现有演员批量获取头像",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  # 为所有演员获取头像（延迟1秒）
  uv run python scripts/backfill_actor_avatars.py

  # 仅处理前10个演员（测试）
  uv run python scripts/backfill_actor_avatars.py --limit 10

  # 干运行模式（不实际修改）
  uv run python scripts/backfill_actor_avatars.py --dry-run --limit 5

  # 加快速度（0.5秒延迟）
  uv run python scripts/backfill_actor_avatars.py --delay 0.5
        """,
    )
    parser.add_argument("--limit", type=int, help="限制处理的演员数量（用于测试）")
    parser.add_argument("--delay", type=float, default=1.0, help="每次刮削之间的延迟秒数（默认1秒）")
    parser.add_argument("--dry-run", action="store_true", help="仅模拟运行，不实际修改数据库或下载文件")
    parser.add_argument("--verbose", action="store_true", help="显示详细日志")

    args = parser.parse_args()

    try:
        backfill_avatars(
            limit=args.limit,
            delay=args.delay,
            dry_run=args.dry_run,
            verbose=args.verbose,
        )
    except KeyboardInterrupt:
        logger.info("\n用户中断")
        sys.exit(0)
    except Exception as e:
        logger.exception(f"执行失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
