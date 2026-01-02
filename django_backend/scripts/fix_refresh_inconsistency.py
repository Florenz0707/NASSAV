#!/usr/bin/env python
"""
修复批量刷新导致的数据不一致问题

问题：
1. file_exists 被错误地重置为 False
2. translation_status 被错误地重置为 pending（即使已有译文）

修复：
1. 检查视频文件是否存在，更新 file_exists 和 file_size
2. 如果有译文但状态是 pending，更新为 completed
"""

import os
import sys
from pathlib import Path

# 设置 Django 环境
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "django_project.settings")

import django

django.setup()

from django.conf import settings
from loguru import logger
from nassav.models import AVResource


def fix_file_exists():
    """修复 file_exists 字段"""
    video_dir = Path(settings.VIDEO_DIR)
    fixed_count = 0

    # 查找所有 file_exists=False 的资源
    resources = AVResource.objects.filter(file_exists=False)
    logger.info(f"检查 {resources.count()} 个标记为未下载的资源...")

    for resource in resources:
        video_path = video_dir / f"{resource.avid}.mp4"
        if video_path.exists():
            # 文件存在但数据库标记为 False
            file_size = video_path.stat().st_size
            resource.file_exists = True
            resource.file_size = file_size
            resource.save(update_fields=["file_exists", "file_size"])
            logger.info(f"修复 {resource.avid}: file_exists=True, size={file_size}")
            fixed_count += 1

    logger.info(f"修复了 {fixed_count} 个资源的 file_exists 字段")
    return fixed_count


def fix_translation_status():
    """修复 translation_status 字段"""
    fixed_count = 0

    # 查找有译文但状态是 pending 的资源
    resources = (
        AVResource.objects.filter(translation_status="pending")
        .exclude(translated_title__isnull=True)
        .exclude(translated_title="")
    )

    logger.info(f"检查 {resources.count()} 个有译文但状态为 pending 的资源...")

    for resource in resources:
        resource.translation_status = "completed"
        resource.save(update_fields=["translation_status"])
        logger.info(f"修复 {resource.avid}: translation_status=completed")
        fixed_count += 1

    logger.info(f"修复了 {fixed_count} 个资源的 translation_status 字段")
    return fixed_count


def main():
    logger.info("开始修复数据不一致问题...")

    file_count = fix_file_exists()
    trans_count = fix_translation_status()

    total = file_count + trans_count
    if total > 0:
        logger.success(
            f"修复完成！共修复 {total} 处不一致（file_exists: {file_count}, translation_status: {trans_count}）"
        )
    else:
        logger.info("未发现需要修复的数据")


if __name__ == "__main__":
    main()
