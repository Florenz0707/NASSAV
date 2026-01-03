"""
Django 管理命令：检查演员头像一致性
"""
import json
from datetime import datetime
from pathlib import Path

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "检查演员头像的一致性，验证 avatar_filename 是否为空或文件是否存在，并可选地下载缺失的头像"

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="实际下载缺失的头像（默认只检查不下载）",
        )
        parser.add_argument(
            "--report",
            type=str,
            default=None,
            help="保存 JSON 报告到指定路径",
        )

    def handle(self, *args, **options):
        from django.conf import settings
        from loguru import logger
        from nassav.constants import ACTOR_AVATAR_PLACEHOLDER_URLS
        from nassav.models import Actor
        from nassav.utils import download_avatar

        apply_changes = options.get("apply", False)
        report_path = options.get(
            "report", "celery_beat/actor_avatars_consistency_report.json"
        )

        self.stdout.write("=" * 60)
        self.stdout.write(f"开始演员头像一致性检查 (apply_changes={apply_changes})")
        self.stdout.write("=" * 60)

        try:
            actors = Actor.objects.all()
            total = actors.count()

            stats = {
                "timestamp": datetime.now().isoformat(),
                "apply_changes": apply_changes,
                "total": total,
                "no_url": 0,
                "placeholder": 0,
                "filename_empty": 0,
                "file_missing": 0,
                "download_success": 0,
                "download_failed": 0,
                "ok": 0,
                "issues": [],
            }

            for idx, actor in enumerate(actors, 1):
                if idx % 100 == 0:
                    self.stdout.write(f"进度: {idx}/{total} ({idx * 100 // total}%)")

                # 检查是否有头像URL
                if not actor.avatar_url:
                    stats["no_url"] += 1
                    continue

                # 检查是否是占位符URL
                if actor.avatar_url in ACTOR_AVATAR_PLACEHOLDER_URLS:
                    stats["placeholder"] += 1
                    continue

                # 检查 avatar_filename 是否为空
                if not actor.avatar_filename:
                    stats["filename_empty"] += 1
                    issue = {
                        "actor": actor.name,
                        "actor_id": actor.id,
                        "issue": "filename_empty",
                        "avatar_url": actor.avatar_url,
                    }

                    # 生成文件名
                    filename = actor.avatar_url.split("/")[-1]
                    if not filename or "." not in filename:
                        filename = f"{actor.id}.jpg"

                    avatar_path = Path(settings.AVATAR_DIR) / filename

                    if apply_changes:
                        if download_avatar(actor.avatar_url, avatar_path):
                            actor.avatar_filename = filename
                            actor.save()
                            stats["download_success"] += 1
                            issue["action"] = "downloaded"
                            issue["filename"] = filename
                        else:
                            stats["download_failed"] += 1
                            issue["action"] = "download_failed"
                    else:
                        issue["action"] = "skipped"
                        issue["would_download_to"] = str(avatar_path)

                    stats["issues"].append(issue)
                    continue

                # 检查文件是否存在
                avatar_path = Path(settings.AVATAR_DIR) / actor.avatar_filename
                if not avatar_path.exists():
                    stats["file_missing"] += 1
                    issue = {
                        "actor": actor.name,
                        "actor_id": actor.id,
                        "issue": "file_missing",
                        "avatar_url": actor.avatar_url,
                        "filename": actor.avatar_filename,
                        "expected_path": str(avatar_path),
                    }

                    if apply_changes:
                        if download_avatar(actor.avatar_url, avatar_path):
                            stats["download_success"] += 1
                            issue["action"] = "redownloaded"
                        else:
                            stats["download_failed"] += 1
                            issue["action"] = "redownload_failed"
                    else:
                        issue["action"] = "skipped"

                    stats["issues"].append(issue)
                else:
                    stats["ok"] += 1

            # 打印统计信息
            self.stdout.write("=" * 60)
            self.stdout.write(self.style.SUCCESS("演员头像一致性检查完成"))
            self.stdout.write(f"  总演员数: {stats['total']}")
            self.stdout.write(f"  没有头像URL: {stats['no_url']}")
            self.stdout.write(f"  占位符URL: {stats['placeholder']}")
            self.stdout.write(f"  filename为空: {stats['filename_empty']}")
            self.stdout.write(f"  文件不存在: {stats['file_missing']}")
            self.stdout.write(f"  下载成功: {stats['download_success']}")
            self.stdout.write(f"  下载失败: {stats['download_failed']}")
            self.stdout.write(f"  状态正常: {stats['ok']}")
            self.stdout.write(f"  问题总数: {len(stats['issues'])}")
            self.stdout.write("=" * 60)

            # 保存报告
            if report_path:
                try:
                    report_file = Path(report_path)
                    report_file.parent.mkdir(parents=True, exist_ok=True)
                    with open(report_file, "w", encoding="utf-8") as f:
                        json.dump(stats, f, ensure_ascii=False, indent=2)
                    self.stdout.write(self.style.SUCCESS(f"报告已保存到: {report_path}"))
                except Exception as e:
                    self.stderr.write(f"保存报告失败: {e}")

        except Exception as e:
            self.stderr.write(self.style.ERROR(f"演员头像一致性检查失败: {e}"))
            raise
