#!/usr/bin/env python3
"""
填充媒体文件字段脚本

功能：
    从 resource/cover 和 resource/video 目录扫描文件，更新 AVResource 的媒体相关字段

更新字段：
    - cover_filename: 封面文件名（只包含文件名，不含路径）
    - file_exists: mp4 文件是否存在
    - file_size: mp4 文件大小（字节）
    - video_saved_at: mp4 文件修改时间

用法：
    # 预览模式（默认）
    uv run python scripts/populate_media_fields.py

    # 实际执行更新
    uv run python scripts/populate_media_fields.py --apply

    # 强制覆盖现有值
    uv run python scripts/populate_media_fields.py --apply --force

    # 限制处理数量
    uv run python scripts/populate_media_fields.py --apply --limit 100

    # 生成 JSON 报告
    uv run python scripts/populate_media_fields.py --apply --report media_report.json

注意：
    - 默认为预览模式（dry-run），不会修改数据库
    - 使用 --apply 才会写入数据库
    - 使用 --force 会覆盖已存在的值
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path


def find_cover(avid: str, cover_root: Path):
    for ext in ["jpg", "jpeg", "png", "webp"]:
        p = cover_root / f"{avid}.{ext}"
        if p.exists():
            return p
    return None


def find_mp4(avid: str, video_root: Path):
    p = video_root / f"{avid}.mp4"
    if p.exists():
        return p
    return None


def main():
    parser = argparse.ArgumentParser(
        description="Populate AVResource media fields from disk"
    )
    parser.add_argument(
        "--apply", action="store_true", help="Write changes to DB (default dry-run)"
    )
    parser.add_argument(
        "--force", action="store_true", help="Overwrite existing DB values"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limit number of records to process (0=all)",
    )
    parser.add_argument("--report", type=str, default=None, help="Write JSON report")
    args = parser.parse_args()

    do_apply = args.apply
    do_force = args.force
    limit = args.limit or None
    report_path = args.report

    # Setup Django environment
    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in os.sys.path:
        os.sys.path.insert(0, str(project_root))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "django_project.settings")
    import django

    django.setup()

    from django.conf import settings
    from django.db import transaction
    from django.utils import timezone
    from nassav.models import AVResource

    cover_root = Path(settings.COVER_DIR)
    video_root = Path(settings.VIDEO_DIR)

    qs = AVResource.objects.all().order_by("id")
    total = qs.count()
    if limit:
        qs = qs[:limit]

    summary = {
        "total": total,
        "checked": 0,
        "updated": 0,
        "skipped": 0,
        "errors": [],
        "items": [],
    }

    for i, obj in enumerate(qs, start=1):
        avid = obj.avid.upper()
        item = {
            "avid": avid,
            "db": {
                "cover_filename": obj.cover_filename,
                "file_exists": obj.file_exists,
                "file_size": obj.file_size,
                "video_saved_at": obj.video_saved_at.isoformat()
                if obj.video_saved_at
                else None,
            },
            "disk": {},
            "actions": [],
        }

        # find disk files
        cover_path = find_cover(avid, cover_root)
        mp4_path = find_mp4(avid, video_root)

        if cover_path:
            item["disk"]["cover"] = str(cover_path.name)
        else:
            item["disk"]["cover"] = None

        if mp4_path:
            item["disk"]["mp4"] = str(mp4_path.name)
            item["disk"]["mp4_size"] = mp4_path.stat().st_size
            item["disk"]["mp4_mtime"] = datetime.fromtimestamp(
                mp4_path.stat().st_mtime
            ).isoformat()
        else:
            item["disk"]["mp4"] = None

        # Decide changes
        changes = {}
        # cover_filename
        if cover_path:
            cover_name = cover_path.name
            if obj.cover_filename != cover_name:
                changes["cover_filename"] = cover_name
        # mp4 presence
        mp4_exists = bool(mp4_path)
        if obj.file_exists != mp4_exists:
            changes["file_exists"] = mp4_exists
        # file_size
        if mp4_path:
            mp4_size = mp4_path.stat().st_size
            if obj.file_size != mp4_size:
                changes["file_size"] = mp4_size
            # video_saved_at from mtime
            mtime = datetime.fromtimestamp(mp4_path.stat().st_mtime)
            if (
                not obj.video_saved_at
                or abs((obj.video_saved_at - mtime).total_seconds()) > 1
            ):
                changes["video_saved_at"] = mtime
        else:
            # if no mp4 on disk but DB says exists, optionally clear if force
            if obj.file_exists and do_force:
                changes["file_exists"] = False
                changes["file_size"] = None
                changes["video_saved_at"] = None

        item["changes"] = changes

        if not changes:
            summary["skipped"] += 1
            summary["items"].append(item)
            summary["checked"] += 1
            continue

        summary["items"].append(item)
        summary["checked"] += 1

        if not do_apply:
            print(f"[DRY] {avid}: will change {list(changes.keys())}")
            continue

        # apply changes
        try:
            with transaction.atomic():
                if "cover_filename" in changes:
                    obj.cover_filename = changes["cover_filename"]
                if "file_exists" in changes:
                    obj.file_exists = changes["file_exists"]
                if "file_size" in changes:
                    obj.file_size = changes["file_size"]
                if "video_saved_at" in changes:
                    obj.video_saved_at = changes["video_saved_at"]
                obj.save()
            summary["updated"] += 1
            print(f"[APPLY] {avid}: updated {list(changes.keys())}")
        except Exception as e:
            summary["errors"].append({"avid": avid, "error": str(e)})
            print(f"[ERROR] {avid}: {e}")

    # final
    print("\nSummary:")
    print(
        f"total: {summary['total']}, checked: {summary['checked']}, updated: {summary['updated']}, skipped: {summary['skipped']}, errors: {len(summary['errors'])}"
    )

    if report_path:
        try:
            with open(report_path, "w", encoding="utf-8") as rf:
                json.dump(summary, rf, ensure_ascii=False, indent=2, default=str)
            print(f"Wrote report to {report_path}")
        except Exception as e:
            print(f"Failed to write report: {e}")


if __name__ == "__main__":
    main()
