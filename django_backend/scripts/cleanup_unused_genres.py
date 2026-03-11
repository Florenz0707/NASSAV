#!/usr/bin/env python
"""
清理无用类别脚本

功能：
    删除数据库中没有关联任何资源的类别（Genre）记录

用法：
    # 预览模式（查看将要删除的类别）
    uv run python scripts/cleanup_unused_genres.py --dry-run

    # 实际执行删除
    uv run python scripts/cleanup_unused_genres.py --execute

    # 只显示统计信息
    uv run python scripts/cleanup_unused_genres.py --stats

    # 导出将要删除的类别到文件
    uv run python scripts/cleanup_unused_genres.py --dry-run --export unused_genres.json

选项：
    --dry-run       预览模式，不实际删除（默认）
    --execute       实际执行删除操作
    --stats         只显示统计信息，不删除
    --export FILE   导出类别列表到 JSON 文件

注意：
    - 默认为预览模式，需要 --execute 才会实际删除
    - 删除操作不可逆，建议先备份数据库
    - 会跳过正在被使用的类别（resource_count > 0）
    - 保留历史记录到 log/cleanup_genres_{timestamp}.log
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# 设置 Django 环境
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "django_project.settings")

import django

django.setup()

from django.db.models import Count
from loguru import logger
from nassav.models import Genre

# 配置日志
logger.remove()
logger.add(sys.stderr, level="INFO")

# 添加文件日志
log_dir = project_root / "log"
log_dir.mkdir(exist_ok=True)
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
log_file = log_dir / f"cleanup_genres_{timestamp}.log"
logger.add(log_file, level="DEBUG")


def get_unused_genres():
    """获取没有关联任何资源的类别"""
    unused = Genre.objects.annotate(resource_count=Count("resources")).filter(
        resource_count=0
    )

    return list(unused)


def get_statistics():
    """获取类别统计信息"""
    total_genres = Genre.objects.count()

    genres_with_count = Genre.objects.annotate(resource_count=Count("resources"))

    used_genres = genres_with_count.filter(resource_count__gt=0).count()
    unused_genres = genres_with_count.filter(resource_count=0).count()

    # 计算资源数量分布
    stats = {
        "total": total_genres,
        "used": used_genres,
        "unused": unused_genres,
        "usage_rate": f"{(used_genres / total_genres * 100) if total_genres > 0 else 0:.2f}%",
    }

    # 获取 top 使用类别
    top_genres = genres_with_count.filter(resource_count__gt=0).order_by(
        "-resource_count"
    )[:10]

    stats["top_10"] = [{"name": g.name, "count": g.resource_count} for g in top_genres]

    return stats


def print_statistics():
    """打印统计信息"""
    stats = get_statistics()

    logger.info("\n" + "=" * 60)
    logger.info("📊 类别统计信息")
    logger.info("=" * 60)
    logger.info(f"总类别数:       {stats['total']}")
    logger.info(f"使用中的类别:   {stats['used']} ({stats['usage_rate']})")
    logger.info(f"未使用的类别:   {stats['unused']}")
    logger.info("\n📈 Top 10 使用最多的类别:")
    for i, item in enumerate(stats["top_10"], 1):
        logger.info(f"  {i:2d}. {item['name']:30s} - {item['count']:4d} 个资源")
    logger.info("=" * 60 + "\n")


def export_genres(genres, filename):
    """导出类别列表到 JSON 文件"""
    data = [
        {
            "id": g.id,
            "name": g.name,
        }
        for g in genres
    ]

    output_path = Path(filename)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    logger.info(f"✓ 已导出 {len(data)} 个类别到 {output_path}")


def cleanup_unused_genres(dry_run=True):
    """清理未使用的类别"""
    logger.info("=" * 60)
    logger.info("🧹 清理未使用的类别")
    logger.info("=" * 60)

    # 获取未使用的类别
    unused_genres = get_unused_genres()

    if not unused_genres:
        logger.info("✓ 没有发现未使用的类别，数据库很干净！")
        return

    logger.info(f"发现 {len(unused_genres)} 个未使用的类别:")
    logger.info("-" * 60)

    # 显示前 20 个，如果太多就省略
    display_limit = 20
    for i, genre in enumerate(unused_genres[:display_limit], 1):
        logger.info(f"  {i:3d}. ID={genre.id:4d} - {genre.name}")

    if len(unused_genres) > display_limit:
        logger.info(f"  ... (还有 {len(unused_genres) - display_limit} 个)")

    logger.info("-" * 60)

    if dry_run:
        logger.warning("\n⚠️  这是预览模式，不会实际删除数据")
        logger.info("使用 --execute 参数来实际执行删除操作")
        logger.info("提示: 可以使用 --export 参数导出列表到文件")
    else:
        logger.warning(f"\n⚠️  即将删除 {len(unused_genres)} 个类别")
        logger.info("开始删除...")

        deleted_count = 0
        failed_count = 0

        for genre in unused_genres:
            try:
                genre_name = genre.name
                genre_id = genre.id
                genre.delete()
                deleted_count += 1
                logger.debug(f"  ✓ 已删除: ID={genre_id} - {genre_name}")
            except Exception as e:
                failed_count += 1
                logger.error(f"  ✗ 删除失败: ID={genre.id} - {genre.name}: {e}")

        logger.info("\n" + "=" * 60)
        logger.info("删除完成统计")
        logger.info("=" * 60)
        logger.info(f"成功删除: {deleted_count}")
        logger.info(f"删除失败: {failed_count}")
        logger.info(f"日志已保存到: {log_file}")
        logger.info("=" * 60 + "\n")

        # 再次显示统计
        logger.info("清理后的统计信息:")
        print_statistics()


def main():
    parser = argparse.ArgumentParser(description="清理数据库中未使用的类别")

    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="预览模式，不实际删除（默认）",
    )
    mode_group.add_argument("--execute", action="store_true", help="实际执行删除操作")
    mode_group.add_argument("--stats", action="store_true", help="只显示统计信息")

    parser.add_argument(
        "--export", type=str, metavar="FILE", help="导出类别列表到 JSON 文件"
    )

    args = parser.parse_args()

    # 只显示统计
    if args.stats:
        print_statistics()
        return

    # 显示清理前的统计
    logger.info("清理前的统计信息:")
    print_statistics()

    # 导出功能
    if args.export:
        unused_genres = get_unused_genres()
        if unused_genres:
            export_genres(unused_genres, args.export)
        else:
            logger.info("没有未使用的类别可以导出")

    # 执行清理
    dry_run = not args.execute
    cleanup_unused_genres(dry_run=dry_run)


if __name__ == "__main__":
    main()
