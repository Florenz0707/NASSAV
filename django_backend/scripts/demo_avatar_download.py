#!/usr/bin/env python3
"""
演示脚本：测试演员头像下载功能

测试流程：
1. 从Javbus刮削一个作品的元数据（包含演员头像URL）
2. 保存到数据库时自动下载头像
3. 验证头像文件是否存在
"""

import os
import sys

import django

# 配置Django环境
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "django_project.settings")
django.setup()

from pathlib import Path

from django.conf import settings
from loguru import logger
from nassav.models import Actor, AVResource
from nassav.scraper.AVDownloadInfo import AVDownloadInfo
from nassav.scraper.Javbus import Javbus


def test_avatar_download():
    """测试头像下载流程"""
    logger.info("=" * 60)
    logger.info("测试演员头像下载功能")
    logger.info("=" * 60)

    # 1. 选择一个测试AVID（ABP-001有演员信息）
    test_avid = "ABP-001"
    logger.info(f"测试AVID: {test_avid}")

    # 2. 从Javbus刮削元数据
    scraper = Javbus()
    scrape_data = scraper.scrape(test_avid)

    if not scrape_data:
        logger.error("刮削失败")
        return False

    logger.info(f"刮削成功: {scrape_data.get('title', '')}")
    logger.info(f"演员数量: {len(scrape_data.get('actors', []))}")

    if "actor_avatars" in scrape_data:
        logger.info(f"头像URL数量: {len(scrape_data['actor_avatars'])}")
        for name, url in scrape_data["actor_avatars"].items():
            logger.info(f"  - {name}: {url}")
    else:
        logger.warning("未找到演员头像URL")
        return False

    # 3. 模拟保存到数据库（只处理演员部分）
    info = AVDownloadInfo(avid=test_avid, source="test")
    info.update_from_scraper(scrape_data)

    # 4. 创建或更新演员记录
    logger.info("\n保存演员信息到数据库...")
    actor_avatars = getattr(info, "actor_avatars", {}) or {}
    downloaded_count = 0

    for actor_name in getattr(info, "actors", []):
        if not actor_name:
            continue

        actor_obj, created = Actor.objects.get_or_create(name=actor_name)
        logger.info(f"{'创建' if created else '更新'} 演员: {actor_name}")

        if actor_name in actor_avatars:
            avatar_url = actor_avatars[actor_name]

            # 更新头像URL
            if actor_obj.avatar_url != avatar_url:
                actor_obj.avatar_url = avatar_url
                filename = avatar_url.rstrip("/").split("/")[-1]
                actor_obj.avatar_filename = filename
                actor_obj.save()
                logger.info(f"  已更新头像URL: {filename}")

                # 下载头像
                from nassav import utils as nassav_utils

                avatar_path = Path(settings.AVATAR_DIR) / filename

                if not avatar_path.exists():
                    logger.info(f"  开始下载头像: {filename}")
                    if nassav_utils.download_avatar(avatar_url, avatar_path):
                        downloaded_count += 1
                        logger.info(f"  ✓ 下载成功: {avatar_path}")
                    else:
                        logger.warning(f"  ✗ 下载失败")
                else:
                    logger.info(f"  头像已存在: {filename}")

    # 5. 验证结果
    logger.info(f"\n本次下载头像数量: {downloaded_count}")

    # 检查AVATAR_DIR中的文件
    avatar_dir = Path(settings.AVATAR_DIR)
    avatar_files = list(avatar_dir.glob("*.jpg"))
    logger.info(f"AVATAR_DIR中的文件总数: {len(avatar_files)}")

    logger.info("\n测试完成！")
    return True


if __name__ == "__main__":
    try:
        test_avatar_download()
    except KeyboardInterrupt:
        logger.info("\n用户中断")
        sys.exit(0)
    except Exception as e:
        logger.exception(f"测试失败: {e}")
        sys.exit(1)
