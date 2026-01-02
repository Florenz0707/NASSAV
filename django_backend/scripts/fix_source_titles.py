#!/usr/bin/env python3
"""
修复现有资源的 source_title 格式，确保以 AVID 开头

用法:
    python scripts/fix_source_titles.py          # 预览模式（不修改数据库）
    python scripts/fix_source_titles.py --execute # 执行修复
    python scripts/fix_source_titles.py --stats   # 统计需要修复的资源数
"""

import argparse
import os
import sys
from pathlib import Path

import django

# 设置 Django 环境
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "django_project.settings")
django.setup()

from nassav.models import AVResource


def normalize_source_title(avid: str, source_title: str) -> str:
    """规范化 source_title，确保以 AVID 开头"""
    if not source_title:
        return source_title

    avid_upper = avid.upper()
    if not source_title.upper().startswith(avid_upper):
        return f"{avid_upper} {source_title}"
    return source_title


def get_resources_needing_fix():
    """获取需要修复的资源列表"""
    resources = AVResource.objects.exclude(source_title__isnull=True).exclude(
        source_title=""
    )

    need_fix = []
    for r in resources:
        avid_upper = r.avid.upper()
        if r.source_title and not r.source_title.upper().startswith(avid_upper):
            need_fix.append(r)

    return need_fix


def show_statistics():
    """显示统计信息"""
    total = AVResource.objects.count()
    with_source_title = (
        AVResource.objects.exclude(source_title__isnull=True)
        .exclude(source_title="")
        .count()
    )
    need_fix = len(get_resources_needing_fix())

    print("=" * 60)
    print("Source Title 统计信息")
    print("=" * 60)
    print(f"总资源数:              {total}")
    print(f"有 source_title 的资源: {with_source_title}")
    print(f"需要修复的资源:        {need_fix}")
    print(f"正确格式的资源:        {with_source_title - need_fix}")
    print("=" * 60)


def preview_fixes():
    """预览需要修复的资源"""
    resources = get_resources_needing_fix()

    if not resources:
        print("✅ 所有 source_title 格式都正确，无需修复！")
        return

    print(f"\n找到 {len(resources)} 个需要修复的资源:")
    print("=" * 80)
    print(f"{'AVID':<15} {'原标题':<35} {'修复后':<35}")
    print("=" * 80)

    for r in resources[:20]:  # 只显示前 20 个
        normalized = normalize_source_title(r.avid, r.source_title)
        print(f"{r.avid:<15} {r.source_title[:33]:<35} {normalized[:33]:<35}")

    if len(resources) > 20:
        print(f"... 以及其他 {len(resources) - 20} 个资源")

    print("=" * 80)
    print(f"\n使用 --execute 参数执行修复")


def execute_fix():
    """执行修复操作"""
    resources = get_resources_needing_fix()

    if not resources:
        print("✅ 所有 source_title 格式都正确，无需修复！")
        return

    print(f"\n开始修复 {len(resources)} 个资源的 source_title...")
    print("=" * 60)

    fixed = 0
    for r in resources:
        old_title = r.source_title
        r.source_title = normalize_source_title(r.avid, r.source_title)
        r.save(update_fields=["source_title"])
        fixed += 1

        if fixed <= 10 or fixed % 100 == 0:  # 显示前 10 个和每 100 个
            print(f"[{fixed:4d}] {r.avid}: {old_title[:30]}")

    print("=" * 60)
    print(f"✅ 修复完成！共修复 {fixed} 个资源")


def main():
    parser = argparse.ArgumentParser(
        description="修复资源的 source_title 格式（确保以 AVID 开头）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("--execute", action="store_true", help="执行修复操作（默认为预览模式）")

    parser.add_argument("--stats", action="store_true", help="显示统计信息")

    args = parser.parse_args()

    if args.stats:
        show_statistics()
    elif args.execute:
        execute_fix()
    else:
        preview_fixes()


if __name__ == "__main__":
    main()
