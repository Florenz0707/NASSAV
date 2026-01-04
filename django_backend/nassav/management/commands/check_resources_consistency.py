"""
Django management command: 检查资源文件与数据库的一致性

用法：
    python manage.py check_resources_consistency [--apply] [--report PATH]

参数：
    --apply: 自动修复发现的问题（默认只检查不修复）
    --report: 指定报告文件路径（默认：celery_beat/resources_consistency_report.json）
"""
import json
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "检查资源文件（封面/视频/缩略图）与数据库的一致性，并可选地自动修复"

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="自动修复发现的问题（默认只检查不修复）",
        )
        parser.add_argument(
            "--report",
            type=str,
            default="celery_beat/resources_consistency_report.json",
            help="报告文件路径（JSON 格式）",
        )

    def handle(self, *args, **options):
        from nassav.models import AVResource

        apply_changes = options.get("apply", False)
        report_path = options.get("report")

        self.stdout.write(self.style.SUCCESS(f"开始检查资源文件一致性... (apply={apply_changes})"))

        cover_dir = Path(settings.COVER_DIR)
        video_dir = Path(settings.VIDEO_DIR)
        thumbnail_dir = Path(
            getattr(settings, "THUMBNAIL_DIR", cover_dir / "thumbnails")
        )

        issues = {
            "cover_missing": [],
            "cover_orphaned": [],
            "video_missing": [],
            "video_orphaned": [],
            "thumbnail_missing": [],
            "db_mismatch": [],
        }

        fixed = {
            "cover_db_updated": 0,
            "video_db_updated": 0,
            "thumbnails_generated": 0,
        }

        # 检查数据库记录对应的文件
        resources = AVResource.objects.all()
        total_resources = resources.count()
        self.stdout.write(f"检查 {total_resources} 个资源...")

        for idx, resource in enumerate(resources, 1):
            if idx % 100 == 0:
                self.stdout.write(f"进度: {idx}/{total_resources}")

            avid = resource.avid

            # 检查封面文件
            cover_found = False
            cover_path = None
            for ext in [".jpg", ".jpeg", ".png", ".webp"]:
                cp = cover_dir / f"{avid}{ext}"
                if cp.exists():
                    cover_found = True
                    cover_path = cp
                    # 检查缩略图
                    for size in ["small", "medium", "large"]:
                        thumb_path = thumbnail_dir / size / f"{avid}.jpg"
                        if not thumb_path.exists():
                            issues["thumbnail_missing"].append(
                                {"avid": avid, "size": size}
                            )
                            if apply_changes:
                                # 生成缩略图
                                try:
                                    from nassav.utils import generate_thumbnail

                                    sizes_map = {
                                        "small": 200,
                                        "medium": 600,
                                        "large": 1200,
                                    }
                                    if generate_thumbnail(
                                        cover_path, thumb_path, sizes_map[size]
                                    ):
                                        fixed["thumbnails_generated"] += 1
                                        self.stdout.write(
                                            self.style.SUCCESS(
                                                f"  生成缩略图: {avid}/{size}"
                                            )
                                        )
                                except Exception as e:
                                    self.stdout.write(
                                        self.style.WARNING(
                                            f"  生成缩略图失败 {avid}/{size}: {e}"
                                        )
                                    )
                    break

            if not cover_found and resource.cover_filename:
                issues["cover_missing"].append(avid)
                if apply_changes:
                    resource.cover_filename = None
                    resource.save(update_fields=["cover_filename"])
                    fixed["cover_db_updated"] += 1
                    self.stdout.write(self.style.WARNING(f"  修复封面字段: {avid}"))

            # 检查视频文件
            video_path = video_dir / f"{avid}.mp4"
            video_exists = video_path.exists()

            if video_exists and not resource.file_exists:
                issues["db_mismatch"].append(
                    {
                        "avid": avid,
                        "type": "video_exists_but_false",
                    }
                )
                if apply_changes:
                    resource.file_exists = True
                    resource.file_size = video_path.stat().st_size
                    resource.video_saved_at = timezone.now()
                    resource.save(
                        update_fields=["file_exists", "file_size", "video_saved_at"]
                    )
                    fixed["video_db_updated"] += 1
                    self.stdout.write(
                        self.style.SUCCESS(f"  修复视频字段: {avid} (存在但标记为False)")
                    )

            elif not video_exists and resource.file_exists:
                issues["db_mismatch"].append(
                    {
                        "avid": avid,
                        "type": "video_missing_but_true",
                    }
                )
                if apply_changes:
                    resource.file_exists = False
                    resource.file_size = None
                    resource.video_saved_at = None
                    resource.save(
                        update_fields=["file_exists", "file_size", "video_saved_at"]
                    )
                    fixed["video_db_updated"] += 1
                    self.stdout.write(
                        self.style.WARNING(f"  修复视频字段: {avid} (不存在但标记为True)")
                    )

        # 检查孤立的文件（数据库中没有记录）
        self.stdout.write("检查孤立文件...")
        db_avids = set(AVResource.objects.values_list("avid", flat=True))

        # 检查孤立的封面
        for cover_file in cover_dir.glob("*"):
            if cover_file.is_file():
                avid = cover_file.stem.upper()
                if avid not in db_avids:
                    issues["cover_orphaned"].append(avid)

        # 检查孤立的视频
        for video_file in video_dir.glob("*.mp4"):
            avid = video_file.stem.upper()
            if avid not in db_avids:
                issues["video_orphaned"].append(avid)

        # 生成报告
        report = {
            "check_time": datetime.now().isoformat(),
            "total_resources": total_resources,
            "apply_changes": apply_changes,
            "issues": {
                "cover_missing": len(issues["cover_missing"]),
                "cover_orphaned": len(issues["cover_orphaned"]),
                "video_missing": len(issues["video_missing"]),
                "video_orphaned": len(issues["video_orphaned"]),
                "thumbnail_missing": len(issues["thumbnail_missing"]),
                "db_mismatch": len(issues["db_mismatch"]),
            },
            "fixed": fixed if apply_changes else None,
            "details": issues,
        }

        # 保存报告
        report_file = Path(settings.BASE_DIR) / report_path
        report_file.parent.mkdir(parents=True, exist_ok=True)
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        # 输出统计
        total_issues = sum(report["issues"].values())
        total_fixed = sum(fixed.values()) if apply_changes else 0

        self.stdout.write(self.style.SUCCESS("\n" + "=" * 60))
        self.stdout.write(self.style.SUCCESS("检查完成！"))
        self.stdout.write(f"总资源数: {total_resources}")
        self.stdout.write(f"发现问题: {total_issues}")
        if apply_changes:
            self.stdout.write(self.style.SUCCESS(f"已修复: {total_fixed}"))
        else:
            self.stdout.write(self.style.WARNING("未修复（使用 --apply 参数自动修复）"))

        self.stdout.write("\n问题详情:")
        for issue_type, count in report["issues"].items():
            if count > 0:
                self.stdout.write(f"  - {issue_type}: {count}")

        if apply_changes and total_fixed > 0:
            self.stdout.write("\n修复详情:")
            for fix_type, count in fixed.items():
                if count > 0:
                    self.stdout.write(f"  - {fix_type}: {count}")

        self.stdout.write(f"\n报告已保存到: {report_file}")
        self.stdout.write(self.style.SUCCESS("=" * 60))
