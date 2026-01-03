import json

from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "检查数据库（AVResource）与磁盘文件（cover/mp4）的一致性，并可选地修复 DB 字段。"

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="将修复写回数据库")
        parser.add_argument("--limit", type=int, default=None, help="仅处理前 N 条记录")
        parser.add_argument("--report", type=str, default=None, help="写入 JSON 报告文件路径")

    def handle(self, *args, **options):
        from django.conf import settings
        from django.db import transaction
        from nassav.models import AVResource

        apply_changes = options.get("apply", False)
        limit = options.get("limit", None)
        report_path = options.get(
            "report", "celery_beat/videos_consistency_report.json"
        )

        qs = AVResource.objects.all().order_by("id")
        total = qs.count()
        if limit:
            qs = qs[:limit]

        from datetime import datetime
        from pathlib import Path

        stats = {
            "timestamp": datetime.now().isoformat(),
            "apply_changes": apply_changes,
            "total": total,
            "checked": 0,
            "file_exists_mismatch": 0,
            "file_size_mismatch": 0,
            "fixed": 0,
            "fix_failed": 0,
            "ok": 0,
            "issues": [],
        }

        cover_root = Path(settings.COVER_DIR)
        video_root = Path(settings.VIDEO_DIR)

        for obj in qs:
            try:
                avid = obj.avid
                mp4_path = video_root / f"{avid}.mp4"
                cover_path = cover_root / (obj.cover_filename or f"{avid}.jpg")

                mp4_exists = mp4_path.exists()
                cover_exists = cover_path.exists()
                mp4_size = mp4_path.stat().st_size if mp4_exists else None

                # Determine discrepancies
                discrepancies = []
                if bool(obj.file_exists) != bool(mp4_exists):
                    discrepancies.append("file_exists_mismatch")
                    stats["file_exists_mismatch"] += 1
                if mp4_exists and obj.file_size != mp4_size:
                    discrepancies.append("file_size_mismatch")
                    stats["file_size_mismatch"] += 1

                if discrepancies:
                    issue = {
                        "avid": avid,
                        "discrepancies": discrepancies,
                        "db_file_exists": obj.file_exists,
                        "mp4_exists": mp4_exists,
                        "db_file_size": obj.file_size,
                        "mp4_size": mp4_size,
                    }

                if discrepancies and apply_changes:
                    try:
                        with transaction.atomic():
                            obj.file_exists = bool(mp4_exists)
                            obj.file_size = mp4_size
                            if mp4_exists:
                                obj.video_saved_at = timezone.now()
                            else:
                                obj.video_saved_at = None
                            obj.save(
                                update_fields=[
                                    "file_exists",
                                    "file_size",
                                    "video_saved_at",
                                ]
                            )
                            stats["fixed"] += 1
                            issue["action"] = "fixed"
                    except Exception as e:
                        stats["fix_failed"] += 1
                        issue["action"] = "fix_failed"
                        issue["error"] = str(e)
                elif discrepancies:
                    issue["action"] = "skipped"

                if discrepancies:
                    stats["issues"].append(issue)
                else:
                    stats["ok"] += 1

                stats["checked"] += 1

            except Exception as e:
                stats["issues"].append(
                    {
                        "avid": getattr(obj, "avid", None),
                        "discrepancies": ["exception"],
                        "error": str(e),
                        "action": "error",
                    }
                )

        # 打印统计信息
        self.stdout.write("=" * 60)
        self.stdout.write(self.style.SUCCESS("视频一致性检查完成"))
        self.stdout.write(f"  总资源数: {stats['total']}")
        self.stdout.write(f"  已检查: {stats['checked']}")
        self.stdout.write(f"  file_exists 不一致: {stats['file_exists_mismatch']}")
        self.stdout.write(f"  file_size 不一致: {stats['file_size_mismatch']}")
        self.stdout.write(f"  修复成功: {stats['fixed']}")
        self.stdout.write(f"  修复失败: {stats['fix_failed']}")
        self.stdout.write(f"  状态正常: {stats['ok']}")
        self.stdout.write(f"  问题总数: {len(stats['issues'])}")
        self.stdout.write("=" * 60)

        if report_path:
            try:
                report_file = Path(report_path)
                report_file.parent.mkdir(parents=True, exist_ok=True)
                with open(report_file, "w", encoding="utf-8") as rf:
                    json.dump(stats, rf, ensure_ascii=False, indent=2)
                self.stdout.write(self.style.SUCCESS(f"报告已保存到: {report_path}"))
            except Exception as e:
                self.stderr.write(f"保存报告失败: {e}")
