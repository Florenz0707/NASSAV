#!/usr/bin/env python3
"""
检查并修复演员头像文件

功能：
1. 检查数据库中所有演员的 avatar_filename 字段
2. 如果为空但有 avatar_url，尝试下载头像
3. 如果不为空，验证文件是否存在，不存在则重新下载
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
from nassav.utils import download_avatar


def fix_actor_avatars(dry_run=False):
    """
    检查并修复演员头像

    Args:
        dry_run: 如果为True，只检查不实际下载
    """
    actors = Actor.objects.all()
    total = actors.count()

    logger.info(f"开始检查 {total} 个演员的头像...")

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
                if download_avatar(actor.avatar_url, avatar_path):
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
        if not avatar_path.exists():
            logger.warning(f"  ⚠ 演员 {actor.name} 的头像文件不存在: {avatar_path}")
            stats["file_missing"] += 1

            if not dry_run:
                logger.info(f"  → 尝试重新下载头像...")
                if download_avatar(actor.avatar_url, avatar_path):
                    logger.info(f"  ✓ 头像重新下载成功: {actor.avatar_filename}")
                    stats["download_success"] += 1
                else:
                    logger.error(f"  ✗ 头像重新下载失败")
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

    args = parser.parse_args()

    # 默认是 dry-run，除非指定 --fix
    dry_run = not args.fix or args.dry_run

    if dry_run:
        logger.info("运行在 DRY-RUN 模式，只检查不修复")
    else:
        logger.info("运行在修复模式，将实际下载缺失的头像")

    fix_actor_avatars(dry_run=dry_run)


if __name__ == "__main__":
    main()
