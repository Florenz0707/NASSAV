#!/usr/bin/env python3
"""
修复视频时长字段脚本

功能：
    修复 AVResource.duration 字段的时长数据

优先策略：
    1. 如果 mp4 文件存在，使用 ffprobe 获取精确时长（秒）
    2. 否则从 metadata 中解析字符串（如 "150分钟"）并转换为秒

用法：
    # 预览模式（不写入数据库）
    uv run python scripts/fix_durations.py --dry-run

    # 实际执行修复
    uv run python scripts/fix_durations.py --apply

    # 限制处理数量
    uv run python scripts/fix_durations.py --apply --limit 100

    # 生成报告
    uv run python scripts/fix_durations.py --dry-run --report duration_report.json

依赖：
    - ffprobe (ffmpeg 工具集)
    安装：sudo apt install ffmpeg

注意：
    - 默认为 --dry-run 模式，不会修改数据库
    - 使用 --apply 才会真正写入数据库
    - 建议先使用 --dry-run 查看效果
"""
import argparse
import json
import os
import sys
from pathlib import Path


def setup_django():
    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "django_project.settings")
    import django

    django.setup()


def parse_duration_to_seconds(raw, mp4_path=None):
    import re
    import subprocess
    from pathlib import Path

    # 如果 mp4 存在，优先使用 ffprobe
    try:
        if mp4_path is not None:
            mp4_path = Path(mp4_path)
            if mp4_path.exists():
                cmd = [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    str(mp4_path),
                ]
                proc = subprocess.run(cmd, capture_output=True, text=True)
                if proc.returncode == 0 and proc.stdout:
                    try:
                        secs = float(proc.stdout.strip())
                        return int(secs)
                    except Exception:
                        pass
    except Exception:
        pass

    if raw is None:
        return None

    try:
        if isinstance(raw, (int, float)):
            return int(raw)
    except Exception:
        pass

    s = str(raw).strip()
    m = re.search(r"(\d+)\s*分钟|(\d+)\s*分", s)
    if m:
        num = m.group(1) or m.group(2)
        try:
            return int(num) * 60
        except Exception:
            pass

    m2 = re.search(r"^(\d+)$", s)
    if m2:
        try:
            return int(m2.group(1)) * 60
        except Exception:
            pass

    nums = re.findall(r"(\d+)", s)
    if nums:
        try:
            return int(nums[0]) * 60
        except Exception:
            pass

    return None


def main():
    parser = argparse.ArgumentParser(description="Fix AVResource.duration")
    parser.add_argument("--apply", action="store_true", help="写入数据库（默认 dry-run）")
    parser.add_argument("--limit", type=int, default=None, help="仅处理前 N 条记录")
    parser.add_argument("--report", type=str, default=None, help="将报告写入 JSON 文件")
    args = parser.parse_args()

    setup_django()
    from django.conf import settings
    from django.db import transaction
    from django.utils import timezone
    from nassav.models import AVResource

    qs = AVResource.objects.all().order_by("id")
    total = qs.count()
    if args.limit:
        qs = qs[: args.limit]

    report = {"total": total, "processed": 0, "updated": 0, "skipped": 0, "errors": []}

    for obj in qs:
        try:
            avid = obj.avid
            resource_dir = Path(settings.RESOURCE_DIR) / avid
            mp4_path = resource_dir / f"{avid}.mp4"

            # 若 mp4 存在且 file_exists True，优先使用 ffprobe
            new_secs = None
            if obj.file_exists and mp4_path.exists():
                new_secs = parse_duration_to_seconds(None, mp4_path=mp4_path)

            # 否则尝试从 metadata 解析
            if new_secs is None:
                md = obj.metadata or {}
                # 常见字段
                raw = md.get("duration") or md.get("time") or md.get("length")
                new_secs = parse_duration_to_seconds(raw)

            report["processed"] += 1

            if new_secs is None:
                report["skipped"] += 1
                continue

            if obj.duration == new_secs:
                report["skipped"] += 1
                continue

            if args.apply:
                try:
                    with transaction.atomic():
                        obj.duration = new_secs
                        obj.metadata_saved_at = timezone.now()
                        obj.save(update_fields=["duration", "metadata_saved_at"])
                        report["updated"] += 1
                        print(f"[APPLY] {avid} duration -> {new_secs}s")
                except Exception as e:
                    report["errors"].append({"avid": avid, "error": str(e)})
            else:
                print(
                    f"[DRY] {avid} would set duration -> {new_secs}s (current: {obj.duration})"
                )

        except Exception as e:
            report["errors"].append(
                {"avid": obj.avid if "obj" in locals() else None, "error": str(e)}
            )

    print("\nSummary:")
    print(json.dumps(report, ensure_ascii=False, indent=2))

    if args.report:
        try:
            with open(args.report, "w", encoding="utf-8") as rf:
                json.dump(report, rf, ensure_ascii=False, indent=2)
            print(f"Report written to {args.report}")
        except Exception as e:
            print(f"Failed to write report: {e}")


if __name__ == "__main__":
    main()
