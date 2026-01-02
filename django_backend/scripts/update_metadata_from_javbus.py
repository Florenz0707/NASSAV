#!/usr/bin/env python
"""
使用 Javbus 更新现有资源的元数据

功能：
1. 扫描 resource 目录下的所有资源文件夹
2. 读取现有的 JSON 元数据
3. 使用 Javbus 刮削新的元数据
4. 合并/更新元数据（保留原有的 m3u8、source 等字段）
5. 保存更新后的元数据

用法：
    python scripts/update_metadata_from_javbus.py [选项]

选项：
    --avid AVID           只更新指定的 AVID
    --dry-run             预览模式，不实际写入文件
    --force               强制更新所有字段（不保留原有值）
    --delay SECONDS       每次请求之间的延迟（默认 2 秒）
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

# 添加项目根目录到 Python 路径
script_dir = Path(__file__).resolve().parent
project_root = script_dir.parent
sys.path.insert(0, str(project_root))

# 设置 Django 环境
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "django_project.settings")

import django

django.setup()

from django.conf import settings
from loguru import logger
from nassav.scraper.Javbus import Javbus

# 配置 loguru
logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{message}</cyan>",
    level="INFO",
)


def get_proxy() -> str | None:
    """从配置获取代理"""
    proxy_config = settings.CONFIG.get("Proxy", {})
    if proxy_config.get("Enable", False):
        return proxy_config.get("url")
    return None


def get_resource_dirs(resource_path: Path) -> list[Path]:
    """兼容函数（旧逻辑）。在 DB-first 模式下通常不使用该函数。"""
    if not resource_path.exists():
        logger.error(f"资源目录不存在: {resource_path}")
        return []

    dirs = []
    for item in resource_path.iterdir():
        if item.is_dir():
            dirs.append(item)
    return sorted(dirs)


def load_metadata_from_db(avid: str) -> dict | None:
    """从数据库加载 `AVResource` 的元数据并构造字典（回退到字段值）。"""
    from nassav.models import AVResource

    resource = AVResource.objects.filter(avid=avid).first()
    if not resource:
        return None
    md = resource.metadata.copy() if resource.metadata else {}
    # Ensure common keys exist
    md.setdefault("avid", resource.avid)
    md.setdefault("title", resource.title or "")  # Scraper 获取的原文标题
    md.setdefault("source_title", resource.source_title or "")  # Source 获取的备用标题
    md.setdefault("translated_title", resource.translated_title or "")  # 翻译后的标题
    md.setdefault("source", resource.source)
    md.setdefault("release_date", resource.release_date)
    md.setdefault("duration", resource.duration)
    md.setdefault("m3u8", resource.m3u8)
    md.setdefault("actors", [a.name for a in resource.actors.all()])
    md.setdefault("genres", [g.name for g in resource.genres.all()])
    return md


def save_metadata_to_db(avid: str, merged_metadata: dict, force: bool = False) -> bool:
    """把合并后的元数据写回到 `AVResource`（包括 actors/genres M2M）。

    注意：
    - title: Scraper 获取的原文标题（日语）
    - source_title: Source 获取的备用标题（保留不修改）
    - translated_title: 翻译后的标题（保留不修改）
    """
    from django.db import transaction
    from nassav.models import Actor, AVResource, Genre

    try:
        with transaction.atomic():
            # 先获取现有记录（如果存在）
            resource_obj, created = AVResource.objects.get_or_create(
                avid=avid, defaults={}
            )

            # 更新字段（注意：只更新 title，不修改 source_title 和 translated_title）
            resource_obj.title = merged_metadata.get("title", "") or ""  # Scraper 原文标题
            resource_obj.source = merged_metadata.get("source", "") or ""
            resource_obj.release_date = merged_metadata.get("release_date", "") or ""
            resource_obj.metadata = merged_metadata
            resource_obj.m3u8 = merged_metadata.get("m3u8", "") or ""

            # 如果有 source_title 或 translated_title，保留原值（不要从 merged_metadata 覆盖）
            # source_title 和 translated_title 由其他流程维护，此脚本不修改

            # duration: try to normalize if numeric-like (keep as-is otherwise)
            try:
                raw_dur = merged_metadata.get("duration")
                if raw_dur is None:
                    resource_obj.duration = None
                else:
                    import re

                    m = re.search(r"(\d+)", str(raw_dur))
                    if m:
                        resource_obj.duration = int(m.group(1)) * 60
            except Exception:
                pass

            # 如果 scraper 更新后，title 有变化且之前有翻译，则重置翻译状态为 pending
            if not created and merged_metadata.get("title"):
                # 重新查询获取旧值（避免缓存）
                old_obj = AVResource.objects.filter(avid=avid).first()
                if (
                    old_obj
                    and old_obj.title
                    and old_obj.title != merged_metadata.get("title")
                ):
                    # 标题变了，重置翻译状态
                    if old_obj.translated_title:
                        resource_obj.translation_status = "pending"
                        resource_obj.translated_title = None
                        logger.info(f"  标题已更新，重置翻译状态为 pending")

            # actors
            resource_obj.actors.clear()
            for a in merged_metadata.get("actors", []) or []:
                if not a:
                    continue
                actor_obj, _ = Actor.objects.get_or_create(name=a)
                resource_obj.actors.add(actor_obj)

            # genres
            resource_obj.genres.clear()
            for g in merged_metadata.get("genres", []) or []:
                if not g:
                    continue
                genre_obj, _ = Genre.objects.get_or_create(name=g)
                resource_obj.genres.add(genre_obj)

            resource_obj.save()
        return True
    except Exception as e:
        logger.error(f"保存元数据到 DB 失败 {avid}: {e}")
        return False


def merge_metadata(original: dict, scraped: dict, force: bool = False) -> dict:
    """
    合并元数据

    原则：
    - 保留原有的 m3u8、source 字段（这些是本地特有的）
    - 如果 force=False，只更新原来为空的字段
    - 如果 force=True，用刮削的数据覆盖所有字段
    """
    # 需要保留的本地字段
    local_fields = ["m3u8", "source"]

    # 字段映射（Javbus -> 本地 JSON）
    # 注意：Javbus scraper 返回的 title 是原文（日语）
    field_mapping = {
        "avid": "avid",
        "title": "title",  # Scraper 原文标题（日语）- 对应 AVResource.title
        "release_date": "release_date",
        "duration": "duration",
        "studio": "studio",  # Javbus 的 studio
        "label": "label",  # Javbus 的 label
        "series": "series",
        "genres": "genres",
        "actors": "actors",
        "director": "director",
    }

    result = original.copy() if original else {}

    for scraped_key, local_key in field_mapping.items():
        scraped_value = scraped.get(scraped_key)

        # 跳过空值
        if not scraped_value:
            continue

        # 跳过本地专有字段
        if local_key in local_fields:
            continue

        # 获取原始值
        original_value = original.get(local_key)

        # 决定是否更新
        if force:
            # 强制模式：直接覆盖
            result[local_key] = scraped_value
        else:
            # 非强制模式：只更新空值
            if not original_value or (
                isinstance(original_value, list) and len(original_value) == 0
            ):
                result[local_key] = scraped_value

    return result


def update_single_resource(
    avid: str,
    resource_path: Path,
    scraper: Javbus,
    dry_run: bool = False,
    force: bool = False,
) -> bool:
    """
    更新单个资源的元数据

    返回是否成功更新
    """
    # 使用数据库中的 AVResource 作为原始元数据
    original_metadata = load_metadata_from_db(avid)
    if original_metadata is None:
        logger.warning(f"数据库中未找到元数据: {avid}")
        return False

    # 从 Javbus 刮削元数据
    logger.info(f"正在刮削 {avid} 的元数据...")
    scraped_metadata = scraper.scrape(avid)

    if scraped_metadata is None:
        logger.error(f"无法从 Javbus 获取 {avid} 的元数据")
        return False

    # 合并元数据
    merged_metadata = merge_metadata(original_metadata, scraped_metadata, force)

    # 显示变更
    logger.info(f"--- {avid} 元数据变更 ---")
    for key in merged_metadata:
        old_val = original_metadata.get(key)
        new_val = merged_metadata.get(key)
        if old_val != new_val:
            logger.info(f"{key} 有变化: {old_val} -> {new_val}")
        else:
            logger.info(f"{key} 未变化: {old_val}")

    # 保存到数据库（如果不是预览模式）
    if not dry_run:
        ok = save_metadata_to_db(avid, merged_metadata, force=force)
        if ok:
            logger.info(f"✓ 已更新 {avid} 的元数据到数据库")
            return True
        else:
            logger.error(f"保存 {avid} 到数据库失败")
            return False
    else:
        logger.info(f"[预览] 将更新 {avid} 的元数据到数据库: {list(merged_metadata.keys())}")
        return True

    return True


def main():
    parser = argparse.ArgumentParser(
        description="使用 Javbus 更新现有资源的元数据",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s                          # 更新所有资源
  %(prog)s --avid SSIS-075          # 只更新指定资源
  %(prog)s --dry-run                # 预览模式
  %(prog)s --force                  # 强制更新所有字段
  %(prog)s --delay 3                # 设置请求间隔为 3 秒
        """,
    )
    parser.add_argument("--avid", type=str, help="只更新指定的 AVID")
    parser.add_argument("--dry-run", action="store_true", help="预览模式，不实际写入文件")
    parser.add_argument("--force", action="store_true", help="强制更新所有字段")
    parser.add_argument("--delay", type=float, default=2.0, help="每次请求之间的延迟（秒）")
    parser.add_argument("--limit", type=int, default=0, help="只处理前 N 个资源（0 表示不限制）")

    args = parser.parse_args()

    # 资源目录（保留用于可能的本地文件操作）
    resource_path = project_root / "resource"

    # 初始化刮削器
    proxy = get_proxy()
    scraper = Javbus(proxy=proxy)

    logger.info(f"资源目录: {resource_path}")
    logger.info(f"代理: {proxy or '未启用'}")
    logger.info(f"预览模式: {'是' if args.dry_run else '否'}")
    logger.info(f"强制更新: {'是' if args.force else '否'}")
    logger.info(f"请求延迟: {args.delay}秒")
    logger.info("-" * 50)

    # 确定要处理的资源列表（DB-first）
    from nassav.models import AVResource

    if args.avid:
        avids = [args.avid.upper()]
    else:
        # 列出数据库中的所有 AVResource 记录
        avids = list(AVResource.objects.values_list("avid", flat=True))

    # 应用限制（如果设置了 --limit）
    if args.limit and args.limit > 0:
        avids = avids[: args.limit]

    logger.info(f"将处理 {len(avids)} 个资源")

    # 统计
    success_count = 0
    fail_count = 0
    skip_count = 0

    for i, avid in enumerate(avids, 1):
        logger.info(f"\n[{i}/{len(avids)}] 处理 {avid}")

        # 在 DB-first 模式下直接处理 AVResource 记录

        try:
            if update_single_resource(
                avid=avid,
                resource_path=resource_path,
                scraper=scraper,
                dry_run=args.dry_run,
                force=args.force,
            ):
                success_count += 1
            else:
                fail_count += 1
        except Exception as e:
            logger.error(f"处理 {avid} 时发生错误: {e}")
            fail_count += 1

        # 请求延迟（避免频繁请求）
        if i < len(avids) and not args.dry_run:
            time.sleep(args.delay)

    # 输出统计
    logger.info("\n" + "=" * 50)
    logger.info(f"处理完成！")
    logger.info(f"  成功: {success_count}")
    logger.info(f"  失败: {fail_count}")
    logger.info(f"  跳过: {skip_count}")


if __name__ == "__main__":
    main()
