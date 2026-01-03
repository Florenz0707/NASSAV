#!/usr/bin/env python3
"""
检查并修复演员头像文件

功能：
1. 检查数据库中所有演员的 avatar_filename 字段
2. 如果为空但有 avatar_url，尝试下载头像
3. 如果不为空，验证文件是否存在，不存在则重新下载
4. 自动过滤占位符URL（nowprinting.gif）

使用方法：
    # 只检查不修复（默认模式）
    python scripts/fix_actor_avatars.py
    python scripts/fix_actor_avatars.py --dry-run

    # 实际执行修复和下载
    python scripts/fix_actor_avatars.py --fix

    # 限制处理数量（测试用）
    python scripts/fix_actor_avatars.py --fix --limit 10

    # 强制重新下载所有头像（即使文件已存在）
    python scripts/fix_actor_avatars.py --fix --force

    # 组合使用
    python scripts/fix_actor_avatars.py --fix --force --limit 5

参数说明：
    --fix         实际执行修复操作（默认只检查不修复）
    --dry-run     只检查不修复（默认模式，可省略）
    --limit N     限制处理的演员数量，用于测试
    --force       强制重新下载所有头像，即使文件已存在

注意事项：
    - 默认运行 DRY-RUN 模式，不会实际下载，只显示需要处理的项
    - 使用 --fix 参数才会实际下载头像
    - --force 参数会重新下载所有头像，请谨慎使用
    - 下载使用配置的代理设置（如果启用）
"""

import os
import sys
from pathlib import Path

# 添加项目路径
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

# 设置 Django 环境
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "django_project.settings")
import django

django.setup()

from django.conf import settings
from loguru import logger
from nassav.constants import ACTOR_AVATAR_PLACEHOLDER_URLS
from nassav.models import Actor
from nassav.scraper.ScraperManager import ScraperManager


def fix_actor_avatars(dry_run=False, limit=None, force=False):
    """
    检查并修复演员头像

    Args:
        dry_run: 如果为True，只检查不实际下载
        limit: 限制处理的演员数量，None表示处理全部
        force: 如果为True，即使文件存在也强制重新下载
    """
    # 初始化 Scraper Manager（用于下载头像）
    proxy = settings.PROXY_URL if settings.PROXY_ENABLED else None
    scraper_manager = ScraperManager(proxy=proxy)

    # 获取第一个可用的 scraper
    scrapers = scraper_manager.get_scrapers()
    if not scrapers:
        logger.error("没有可用的刮削器，无法下载头像")
        return
    _, scraper = scrapers[0]

    actors = Actor.objects.all()
    if limit:
        actors = actors[:limit]

    total = actors.count()

    logger.info(f"开始检查 {total} 个演员的头像...")
    logger.info(f"使用刮削器: {scraper.get_scraper_name()}")
    if force:
        logger.info("强制模式：将重新下载所有头像（即使文件已存在）")

    stats = {
        "total": total,
        "no_url": 0,  # 没有头像URL
        "placeholder": 0,  # 占位符URL
        "filename_empty": 0,  # filename为空
        "file_missing": 0,  # 文件不存在
        "download_success": 0,  # 下载成功
        "download_failed": 0,  # 下载失败
        "ok": 0,  # 一切正常
    }

    for idx, actor in enumerate(actors, 1):
        logger.info(f"[{idx}/{total}] 检查演员: {actor.name}")

        # 检查是否有头像URL
        if not actor.avatar_url:
            logger.debug(f"  ✗ 演员 {actor.name} 没有头像URL")
            stats["no_url"] += 1
            continue

        # 检查是否是占位符URL
        if actor.avatar_url in ACTOR_AVATAR_PLACEHOLDER_URLS:
            logger.debug(f"  ✗ 演员 {actor.name} 的头像是占位符URL")
            stats["placeholder"] += 1
            continue

        # 检查 avatar_filename 是否为空
        if not actor.avatar_filename:
            logger.warning(
                f"  ⚠ 演员 {actor.name} 的 avatar_filename 为空，但有URL: {actor.avatar_url}"
            )
            stats["filename_empty"] += 1

            # 生成文件名
            filename = actor.avatar_url.split("/")[-1]
            if not filename or "." not in filename:
                filename = f"{actor.id}.jpg"

            avatar_path = Path(settings.AVATAR_DIR) / filename

            if not dry_run:
                logger.info(f"  → 尝试下载头像到: {avatar_path}")
                if scraper.download_avatar(actor.avatar_url, str(avatar_path)):
                    actor.avatar_filename = filename
                    actor.save()
                    logger.info(f"  ✓ 头像下载成功并更新数据库: {filename}")
                    stats["download_success"] += 1
                else:
                    logger.error(f"  ✗ 头像下载失败")
                    stats["download_failed"] += 1
            else:
                logger.info(f"  [DRY-RUN] 将下载: {actor.avatar_url} -> {avatar_path}")
            continue

        # 检查文件是否存在
        avatar_path = Path(settings.AVATAR_DIR) / actor.avatar_filename
        if not avatar_path.exists() or force:
            if force and avatar_path.exists():
                logger.info(f"  ⚠ 演员 {actor.name} 的头像文件存在，但强制重新下载")
                stats["file_missing"] += 1  # 强制下载也计入 file_missing
            else:
                logger.warning(f"  ⚠ 演员 {actor.name} 的头像文件不存在: {avatar_path}")
                stats["file_missing"] += 1

            if not dry_run:
                logger.info(f"  → 尝试{'重新' if avatar_path.exists() else ''}下载头像...")
                if scraper.download_avatar(actor.avatar_url, str(avatar_path)):
                    logger.info(
                        f"  ✓ 头像{'重新' if force else ''}下载成功: {actor.avatar_filename}"
                    )
                    stats["download_success"] += 1
                else:
                    logger.error(f"  ✗ 头像下载失败")
                    stats["download_failed"] += 1
            else:
                logger.info(f"  [DRY-RUN] 将重新下载: {actor.avatar_url} -> {avatar_path}")
        else:
            logger.debug(f"  ✓ 演员 {actor.name} 的头像文件正常")
            stats["ok"] += 1

    # 打印统计信息
    logger.info("=" * 60)
    logger.info("检查完成，统计结果：")
    logger.info(f"  总演员数: {stats['total']}")
    logger.info(f"  没有头像URL: {stats['no_url']}")
    logger.info(f"  占位符URL: {stats['placeholder']}")
    logger.info(f"  filename为空: {stats['filename_empty']}")
    logger.info(f"  文件不存在: {stats['file_missing']}")
    logger.info(f"  下载成功: {stats['download_success']}")
    logger.info(f"  下载失败: {stats['download_failed']}")
    logger.info(f"  状态正常: {stats['ok']}")
    logger.info("=" * 60)

    if dry_run:
        logger.info("这是DRY-RUN模式，没有实际执行下载操作")
        logger.info("要执行实际下载，请运行: python scripts/fix_actor_avatars.py --fix")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="检查并修复演员头像文件")
    parser.add_argument(
        "--fix",
        action="store_true",
        help="实际执行修复操作（默认只检查不修复）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只检查不修复（默认模式）",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="限制处理的演员数量（例如 --limit 10）",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="强制重新下载所有头像，即使文件已存在",
    )

    args = parser.parse_args()

    # 默认是 dry-run，除非指定 --fix
    dry_run = not args.fix or args.dry_run

    if dry_run:
        logger.info("运行在 DRY-RUN 模式，只检查不修复")
    else:
        logger.info("运行在修复模式，将实际下载缺失的头像")

    fix_actor_avatars(dry_run=dry_run, limit=args.limit, force=args.force)


if __name__ == "__main__":
    main()
