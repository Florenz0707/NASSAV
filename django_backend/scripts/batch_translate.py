#!/usr/bin/env python
"""
批量翻译脚本 - 使用 Celery 异步任务翻译未翻译的资源标题

用法:
    # 翻译所有待翻译的资源
    uv run python scripts/batch_translate.py

    # 限制翻译数量
    uv run python scripts/batch_translate.py --limit 10

    # 指定 AVID 列表
    uv run python scripts/batch_translate.py --avids ABC-001 DEF-002 GHI-003

    # 同步模式（不使用 Celery）
    uv run python scripts/batch_translate.py --sync

    # 重新翻译已翻译的资源
    uv run python scripts/batch_translate.py --force

    # 查看状态统计
    uv run python scripts/batch_translate.py --status

    # 预览模式（不实际翻译，仅显示预处理结果）
    uv run python scripts/batch_translate.py --sync --dry-run
    uv run python scripts/batch_translate.py --sync --dry-run --limit 5

注意: 使用 Celery 异步模式前需要启动 worker:
    uv run celery -A django_project worker -l info
"""

import argparse
import os
import sys
import time

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Django 设置
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "django_project.settings")

import django

django.setup()

from nassav.models import AVResource
from nassav.tasks import batch_translate_titles_task


def get_status_stats():
    """获取翻译状态统计"""
    stats = {}
    for status in ["pending", "translating", "completed", "failed", "skipped"]:
        count = AVResource.objects.filter(translation_status=status).count()
        stats[status] = count
    return stats


def print_status():
    """打印翻译状态统计"""
    stats = get_status_stats()
    total = sum(stats.values())

    print("\n" + "=" * 50)
    print("📊 翻译状态统计")
    print("=" * 50)
    print(f"  ⏳ 待翻译 (pending):     {stats['pending']:>5}")
    print(f"  🔄 翻译中 (translating): {stats['translating']:>5}")
    print(f"  ✅ 已完成 (completed):   {stats['completed']:>5}")
    print(f"  ❌ 失败 (failed):        {stats['failed']:>5}")
    print(f"  ⏭️  跳过 (skipped):       {stats['skipped']:>5}")
    print("-" * 50)
    print(f"  📦 总计:                 {total:>5}")
    print("=" * 50 + "\n")


def get_pending_resources(limit=None, force=False):
    """
    获取待翻译的资源

    Args:
        limit: 限制数量
        force: 是否包括已翻译的
    """
    from django.db.models import Q

    # 必须有标题
    query = (Q(original_title__isnull=False) & ~Q(original_title="")) | (
        Q(source_title__isnull=False) & ~Q(source_title="")
    )

    if not force:
        # 只查询 pending 或 failed 状态的
        query &= Q(translation_status__in=["pending", "failed"])

    resources = AVResource.objects.filter(query)

    if limit:
        resources = resources[:limit]

    return list(resources)


def run_sync_translation(resources, verbose=True):
    """
    同步模式翻译

    Args:
        resources: 资源列表
        verbose: 是否显示详细信息
    """
    from nassav.translator import translator_manager

    total = len(resources)
    success = 0
    failed = 0

    print(f"\n🔄 开始同步翻译 {total} 条记录...\n")

    for idx, resource in enumerate(resources, 1):
        title = resource.original_title or resource.source_title
        if not title:
            if verbose:
                print(f"  [{idx}/{total}] ⏭️  {resource.avid}: 无标题，跳过")
            resource.translation_status = "skipped"
            resource.save(update_fields=["translation_status"])
            continue

        # 更新状态为翻译中
        resource.translation_status = "translating"
        resource.save(update_fields=["translation_status"])

        try:
            translated = translator_manager.translate(title)
            if translated:
                resource.translated_title = translated
                resource.translation_status = "completed"
                resource.save(update_fields=["translated_title", "translation_status"])
                success += 1
                if verbose:
                    print(f"  [{idx}/{total}] ✅ {resource.avid}")
                    print(f"              原文: {title[:40]}...")
                    print(f"              译文: {translated[:40]}...")
            else:
                resource.translation_status = "failed"
                resource.save(update_fields=["translation_status"])
                failed += 1
                if verbose:
                    print(f"  [{idx}/{total}] ❌ {resource.avid}: 翻译返回空")
        except Exception as e:
            resource.translation_status = "failed"
            resource.save(update_fields=["translation_status"])
            failed += 1
            if verbose:
                print(f"  [{idx}/{total}] ❌ {resource.avid}: {e}")

    print(f"\n✅ 同步翻译完成: 成功 {success}, 失败 {failed}\n")
    return {"success": success, "failed": failed}


def run_dry_run(resources, verbose=True):
    """
    预览模式 - 显示原标题、原译文和预览译文（实际调用翻译但不保存）

    Args:
        resources: 资源列表
        verbose: 是否显示详细信息
    """
    from nassav.translator import translator_manager

    total = len(resources)
    print(f"\n🔍 预览模式 (dry-run) - 共 {total} 条记录\n")
    print("=" * 80)

    for idx, resource in enumerate(resources, 1):
        title = resource.original_title or resource.source_title
        avid = resource.avid
        current_translation = resource.translated_title

        print(f"\n[{idx}/{total}] {avid}")

        if not title:
            print("  ⏭️  无标题，将跳过")
            continue

        print(f"  原标题: {title}")

        if current_translation:
            print(f"  原译文: {current_translation}")
        else:
            print("  原译文: (无)")

        # 调用翻译器获取预览译文
        try:
            preview_translation = translator_manager.translate(title)
            if preview_translation:
                print(f"  预览译文: {preview_translation}")
                if current_translation and current_translation != preview_translation:
                    print("  📝 译文有变化")
            else:
                print("  预览译文: ❌ 翻译失败")
        except Exception as e:
            print(f"  预览译文: ❌ 错误: {e}")

    print("\n" + "=" * 80)
    print(f"\n📊 预览完成: 共 {total} 条记录")


def run_async_translation(resources=None, avids=None, skip_existing=True):
    """
    异步模式翻译（使用 Celery）

    Args:
        resources: 资源列表（用于获取 avids）
        avids: 直接指定的 AVID 列表
        skip_existing: 是否跳过已翻译的
    """
    if avids is None and resources:
        avids = [r.avid for r in resources]

    total = (
        len(avids)
        if avids
        else AVResource.objects.filter(
            translation_status__in=["pending", "failed"]
        ).count()
    )

    print("\n🚀 提交 Celery 异步翻译任务...")
    print(f"   待翻译数量: {total}")

    try:
        # 提交批量翻译任务
        task_result = batch_translate_titles_task.delay(
            avids=avids, skip_existing=skip_existing
        )

        print(f"   任务 ID: {task_result.id}")
        print("\n⏳ 等待任务完成...\n")

        # 等待任务完成并获取结果
        start_time = time.time()
        while not task_result.ready():
            elapsed = time.time() - start_time
            stats = get_status_stats()
            print(
                f"\r   已用时间: {elapsed:.1f}s | "
                f"完成: {stats['completed']} | "
                f"翻译中: {stats['translating']} | "
                f"失败: {stats['failed']}",
                end="",
                flush=True,
            )
            time.sleep(2)

        print()  # 换行

        result = task_result.result

        if result and result.get("success"):
            print("\n✅ 批量翻译任务完成!")
            print(f"   总计: {result.get('total', 0)}")
            print(f"   成功: {result.get('translated', 0)}")
            print(f"   失败: {result.get('failed', 0)}")
            print(f"   跳过: {result.get('skipped', 0)}")
        else:
            error = result.get("error", "未知错误") if result else "任务返回空"
            print(f"\n❌ 批量翻译任务失败: {error}")

        return result

    except Exception as e:
        print(f"\n❌ 提交 Celery 任务失败: {e}")
        print("   请确保 Celery worker 已启动:")
        print("   uv run celery -A django_project worker -l info")
        return None


def main():
    parser = argparse.ArgumentParser(
        description="批量翻译资源标题",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s                      # 翻译所有待翻译的资源
  %(prog)s --limit 10           # 只翻译前 10 条
  %(prog)s --avids ABC-001      # 翻译指定 AVID
  %(prog)s --sync               # 同步模式（不使用 Celery）
  %(prog)s --sync --dry-run     # 预览模式，显示预处理结果
  %(prog)s --status             # 只显示状态统计
  %(prog)s --force              # 重新翻译已完成的
        """,
    )

    parser.add_argument("--limit", "-l", type=int, default=None, help="限制翻译数量")

    parser.add_argument(
        "--avids", "-a", nargs="+", default=None, help="指定要翻译的 AVID 列表"
    )

    parser.add_argument(
        "--sync", "-s", action="store_true", help="使用同步模式（不需要 Celery worker）"
    )

    parser.add_argument(
        "--force", "-f", action="store_true", help="强制重新翻译（包括已翻译的）"
    )

    parser.add_argument("--status", action="store_true", help="只显示翻译状态统计")

    parser.add_argument("--quiet", "-q", action="store_true", help="静默模式，减少输出")

    parser.add_argument(
        "--dry-run",
        "-d",
        action="store_true",
        help="预览模式，显示预处理结果但不实际翻译（需配合 --sync 使用）",
    )

    args = parser.parse_args()

    # 显示当前状态
    print_status()

    # 只查看状态
    if args.status:
        return

    # 获取待翻译资源
    if args.avids:
        # 指定 AVID
        avids = [a.upper() for a in args.avids]
        resources = list(AVResource.objects.filter(avid__in=avids))
        if not resources:
            print(f"❌ 未找到指定的资源: {args.avids}")
            return
        print(f"📋 已指定 {len(resources)} 个 AVID")
    else:
        # 获取待翻译资源
        resources = get_pending_resources(limit=args.limit, force=args.force)
        if not resources:
            print("✅ 没有需要翻译的资源")
            return
        print(f"📋 找到 {len(resources)} 条待翻译记录")

    # 显示待翻译列表
    if not args.quiet:
        print("\n待翻译资源预览:")
        for r in resources[:5]:
            title = r.title or r.source_title or "无标题"
            print(f"  - {r.avid}: {title[:50]}...")
        if len(resources) > 5:
            print(f"  ... 还有 {len(resources) - 5} 条")

    # dry-run 模式检查
    if args.dry_run:
        if not args.sync:
            print("⚠️  --dry-run 需要配合 --sync 使用")
            return
        run_dry_run(resources, verbose=not args.quiet)
        return

    # 确认执行
    if not args.quiet:
        try:
            confirm = input(f"\n确认开始翻译 {len(resources)} 条记录? [y/N]: ")
            if confirm.lower() != "y":
                print("已取消")
                return
        except EOFError:
            # 非交互模式
            pass

    # 执行翻译
    if args.sync:
        # 同步模式
        run_sync_translation(resources, verbose=not args.quiet)
    else:
        # 异步模式
        avids = [r.avid for r in resources] if args.avids or args.limit else None
        run_async_translation(avids=avids, skip_existing=not args.force)

    # 显示最终状态
    print_status()


if __name__ == "__main__":
    main()
