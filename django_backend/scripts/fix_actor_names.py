#!/usr/bin/env python
"""
修复数据库中被截断的演员名称

功能：
1. 维护一个"确认正常"的名称集合（完整的、括号成对的名称）
2. 从 nassav_avresource 表中的 avid 进行遍历
3. 如果某 AV 涉及到的演员不存在于"确认正常"的集合中，则尝试重新刮削
4. 使用新刮削的数据更新演员信息（只更新演员，不修改其他字段）

注意：
- 本脚本只专注于修复演员名称，不会修改 title、duration、genres 等其他字段
- 修复后，旧的被截断的 Actor 记录会保留在数据库中（但不再有资源关联）
- 如需清理未使用的 Actor 记录，请使用其他维护脚本

用法：
    # 预览模式（不实际修改）
    uv run python scripts/fix_actor_names.py --dry-run

    # 实际执行修复
    uv run python scripts/fix_actor_names.py

    # 只修复指定的 AVID
    uv run python scripts/fix_actor_names.py --avid ABC-001

    # 批量修复多个 AVID
    uv run python scripts/fix_actor_names.py --avids ABC-001 DEF-002 GHI-003

    # 显示统计信息
    uv run python scripts/fix_actor_names.py --stats

    # 修复时增加延迟（避免频繁请求）
    uv run python scripts/fix_actor_names.py --delay 3

    # 强制重新刮削所有资源（即使演员名看起来正常）
    uv run python scripts/fix_actor_names.py --force

    # 详细输出模式
    uv run python scripts/fix_actor_names.py --verbose
"""

import argparse
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
from django.db import transaction
from loguru import logger
from nassav.models import Actor, AVResource
from nassav.scraper.ScraperManager import ScraperManager

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


def is_actor_name_normal(name: str) -> bool:
    """
    判断演员名是否正常（未被截断）

    规则：
    1. 如果包含左括号"（"，必须有相同数量的右括号"）"
    2. 如果包含左括号"("，必须有相同数量的右括号")"
    3. 名称不应该以括号结尾（除非括号是成对的）

    返回：
        True: 名称正常
        False: 名称可能被截断
    """
    if not name:
        return True

    # 检查全角括号
    open_count_full = name.count("（")
    close_count_full = name.count("）")
    if open_count_full != close_count_full:
        return False

    # 检查半角括号
    open_count_half = name.count("(")
    close_count_half = name.count(")")
    if open_count_half != close_count_half:
        return False

    # 检查是否以未闭合的括号结尾
    if name.endswith("（") or name.endswith("("):
        return False

    return True


def get_abnormal_actors() -> set:
    """
    获取所有异常（可能被截断）的演员名称集合

    返回：
        包含异常演员名称的集合
    """
    abnormal_actors = set()
    all_actors = Actor.objects.all()

    for actor in all_actors:
        if not is_actor_name_normal(actor.name):
            abnormal_actors.add(actor.name)

    return abnormal_actors


def get_normal_actors() -> set:
    """
    获取所有正常的演员名称集合

    返回：
        包含正常演员名称的集合
    """
    normal_actors = set()
    all_actors = Actor.objects.all()

    for actor in all_actors:
        if is_actor_name_normal(actor.name):
            normal_actors.add(actor.name)

    return normal_actors


def needs_rescrape(resource: AVResource, normal_actors: set) -> tuple[bool, list]:
    """
    判断资源是否需要重新刮削

    参数：
        resource: AVResource 实例
        normal_actors: 正常演员名称集合

    返回：
        (需要重新刮削, 异常演员列表)
    """
    abnormal_actors = []

    for actor in resource.actors.all():
        if actor.name not in normal_actors:
            if not is_actor_name_normal(actor.name):
                abnormal_actors.append(actor.name)

    return len(abnormal_actors) > 0, abnormal_actors


def rescrape_and_update(
    resource: AVResource, scraper_manager: ScraperManager, dry_run: bool = False
) -> tuple[bool, str]:
    """
    重新刮削并更新资源的演员信息

    参数：
        resource: AVResource 实例
        scraper_manager: 刮削器管理器
        dry_run: 是否为预览模式

    返回：
        (是否成功, 消息)
    """
    avid = resource.avid

    try:
        # 重新刮削元数据
        logger.info(f"正在刮削 {avid} 的元数据...")
        metadata = scraper_manager.scrape(avid)

        if not metadata:
            return False, "刮削失败：未获取到元数据"

        new_actors = metadata.get("actors", [])
        if not new_actors:
            return False, "刮削失败：未获取到演员信息"

        # 检查新数据中的演员名是否正常
        abnormal_in_new = [a for a in new_actors if not is_actor_name_normal(a)]
        if abnormal_in_new:
            return (
                False,
                f"刮削到的数据仍有异常演员名: {', '.join(abnormal_in_new)}",
            )

        if dry_run:
            logger.info(f"[DRY-RUN] 将更新 {avid} 的演员信息:")
            logger.info(f"  旧演员: {[a.name for a in resource.actors.all()]}")
            logger.info(f"  新演员: {new_actors}")
            return True, "预览模式：不实际更新"

        # 实际更新数据库（只更新演员信息，不修改其他字段）
        with transaction.atomic():
            # 清空现有演员关联
            resource.actors.clear()

            # 添加新的演员
            for actor_name in new_actors:
                actor, created = Actor.objects.get_or_create(name=actor_name)
                resource.actors.add(actor)

            # 注意：不更新其他元数据字段（title, duration, genres等）
            # 本脚本只专注于修复演员名称

        logger.success(f"✓ 已更新 {avid} 的演员信息")
        logger.info(f"  新演员: {', '.join(new_actors)}")
        return True, "更新成功"

    except Exception as e:
        logger.error(f"处理 {avid} 时出错: {e}")
        return False, f"异常: {str(e)}"


def print_statistics():
    """打印统计信息"""
    all_actors = Actor.objects.all()
    total_actors = all_actors.count()

    normal_count = 0
    abnormal_count = 0
    abnormal_examples = []

    for actor in all_actors:
        if is_actor_name_normal(actor.name):
            normal_count += 1
        else:
            abnormal_count += 1
            if len(abnormal_examples) < 10:
                abnormal_examples.append(actor.name)

    # 统计涉及异常演员的资源数
    resources_with_abnormal = set()
    for actor in all_actors:
        if not is_actor_name_normal(actor.name):
            resources_with_abnormal.update(
                actor.resources.values_list("avid", flat=True)
            )

    print("\n" + "=" * 70)
    print("📊 演员名称统计")
    print("=" * 70)
    print(f"  总演员数:           {total_actors:>6}")
    print(f"  ✅ 正常演员数:       {normal_count:>6}")
    print(f"  ❌ 异常演员数:       {abnormal_count:>6}")
    print(f"  📦 涉及异常的资源数: {len(resources_with_abnormal):>6}")
    print("=" * 70)

    if abnormal_examples:
        print("\n异常演员示例（可能被截断）:")
        for name in abnormal_examples:
            print(f"  - {name}")
        if abnormal_count > len(abnormal_examples):
            print(f"  ... 还有 {abnormal_count - len(abnormal_examples)} 个")

    print()


def main():
    parser = argparse.ArgumentParser(
        description="修复数据库中被截断的演员名称",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("--dry-run", action="store_true", help="预览模式，不实际修改数据")
    parser.add_argument("--avid", type=str, help="只处理指定的 AVID")
    parser.add_argument("--avids", nargs="+", help="批量处理多个 AVID")
    parser.add_argument("--stats", action="store_true", help="只显示统计信息")
    parser.add_argument("--delay", type=float, default=2.0, help="每次刮削之间的延迟（秒），默认 2")
    parser.add_argument("--force", action="store_true", help="强制重新刮削所有资源（即使演员名看起来正常）")
    parser.add_argument("--verbose", action="store_true", help="详细输出模式")
    parser.add_argument("--limit", type=int, help="限制处理的资源数量")

    args = parser.parse_args()

    # 设置日志级别
    if args.verbose:
        logger.remove()
        logger.add(
            sys.stderr,
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{message}</cyan>",
            level="DEBUG",
        )

    # 只显示统计信息
    if args.stats:
        print_statistics()
        return

    # 初始化刮削器
    proxy = get_proxy()
    scraper_manager = ScraperManager(proxy)

    # 获取正常演员集合
    logger.info("正在构建正常演员名称集合...")
    normal_actors = get_normal_actors()
    abnormal_actors = get_abnormal_actors()
    logger.info(f"正常演员数: {len(normal_actors)}")
    logger.info(f"异常演员数: {len(abnormal_actors)}")

    if args.dry_run:
        logger.warning("⚠️  预览模式：不会实际修改数据")

    # 确定要处理的资源
    if args.avid:
        resources = AVResource.objects.filter(avid=args.avid.upper())
    elif args.avids:
        avids_upper = [avid.upper() for avid in args.avids]
        resources = AVResource.objects.filter(avid__in=avids_upper)
    else:
        resources = AVResource.objects.all()

    if args.limit:
        resources = resources[: args.limit]

    total_resources = resources.count()
    logger.info(f"待检查的资源总数: {total_resources}")

    # 统计变量
    checked = 0
    needs_fix = 0
    fixed = 0
    failed = 0
    skipped = 0

    # 遍历处理
    for resource in resources:
        checked += 1
        avid = resource.avid

        # 检查是否需要重新刮削
        if args.force:
            need_rescrape = True
            abnormal_list = ["强制模式"]
        else:
            need_rescrape, abnormal_list = needs_rescrape(resource, normal_actors)

        if not need_rescrape:
            if args.verbose:
                logger.debug(f"[{checked}/{total_resources}] {avid}: 演员名正常，跳过")
            skipped += 1
            continue

        needs_fix += 1
        logger.info(f"[{checked}/{total_resources}] {avid}: 发现异常演员 {abnormal_list}")

        # 重新刮削并更新
        success, message = rescrape_and_update(resource, scraper_manager, args.dry_run)

        if success:
            fixed += 1
            logger.success(f"  ✓ {message}")
        else:
            failed += 1
            logger.error(f"  ✗ {message}")

        # 延迟
        if checked < total_resources:
            time.sleep(args.delay)

    # 打印最终统计
    print("\n" + "=" * 70)
    print("📊 处理结果统计")
    print("=" * 70)
    print(f"  检查资源数:     {checked:>6}")
    print(f"  需要修复:       {needs_fix:>6}")
    print(f"  ✅ 成功修复:     {fixed:>6}")
    print(f"  ❌ 修复失败:     {failed:>6}")
    print(f"  ⏭️  跳过:         {skipped:>6}")
    print("=" * 70)

    if args.dry_run:
        print("\n⚠️  这是预览模式，未实际修改数据")
        print("   移除 --dry-run 参数以实际执行修复\n")


if __name__ == "__main__":
    main()
