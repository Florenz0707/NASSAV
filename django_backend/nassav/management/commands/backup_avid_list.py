"""
Django management command: 备份数据库中的 AVID 列表

用法：
    python manage.py backup_avid_list [--days DAYS]

参数：
    --days: 备份文件保留天数（默认：30 天）

备份格式：
    - JSON 文件: backup/avid_backup_{timestamp}.json
"""
import json
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "备份数据库中所有 AVID 列表到文件（用于灾难恢复）"

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=30,
            help="备份文件保留天数（默认：30）",
        )

    def handle(self, *args, **options):
        from nassav.models import AVResource

        days = options.get("days", 30)

        try:
            # 创建备份目录
            backup_dir = Path(settings.BASE_DIR) / "backup"
            backup_dir.mkdir(parents=True, exist_ok=True)

            self.stdout.write(self.style.SUCCESS("开始备份 AVID 列表..."))

            # 获取所有 AVID（按字母顺序排序）
            avids = list(
                AVResource.objects.values_list("avid", flat=True).order_by("avid")
            )
            total_count = len(avids)

            if total_count == 0:
                self.stdout.write(self.style.WARNING("数据库中没有资源，跳过备份"))
                return

            # 生成时间戳
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            # 保存为 JSON 格式（包含更多元信息）
            json_file = backup_dir / f"avid_backup_{timestamp}.json"
            backup_data = {
                "backup_time": timestamp,
                "backup_datetime": datetime.now().isoformat(),
                "total_count": total_count,
                "avids": avids,
            }
            with open(json_file, "w", encoding="utf-8") as f:
                json.dump(backup_data, f, ensure_ascii=False, indent=2)

            self.stdout.write(self.style.SUCCESS(f"  已保存 JSON 格式: {json_file.name}"))

            # 清理旧备份
            deleted_count = self.cleanup_old_backups(backup_dir, days)

            # 输出统计
            self.stdout.write(self.style.SUCCESS("\n" + "=" * 60))
            self.stdout.write(self.style.SUCCESS("备份完成！"))
            self.stdout.write(f"备份资源数: {total_count}")
            self.stdout.write(f"备份文件: {json_file}")
            if deleted_count > 0:
                self.stdout.write(self.style.WARNING(f"已清理 {deleted_count} 个旧备份文件"))
            self.stdout.write(f"备份保留策略: 保留最近 {days} 天")
            self.stdout.write(self.style.SUCCESS("=" * 60))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"备份失败: {e}"))
            raise

    def cleanup_old_backups(self, backup_dir: Path, days: int = 30) -> int:
        """
        清理旧的备份文件

        Args:
            backup_dir: 备份目录路径
            days: 保留天数

        Returns:
            删除的文件数量
        """
        import time

        try:
            cutoff_time = time.time() - (days * 86400)
            deleted_count = 0

            # 只清理 JSON 备份文件
            for file in backup_dir.glob("avid_backup_*.json"):
                if file.stat().st_mtime < cutoff_time:
                    try:
                        file.unlink()
                        deleted_count += 1
                        self.stdout.write(self.style.WARNING(f"  已删除旧备份: {file.name}"))
                    except Exception as e:
                        self.stdout.write(
                            self.style.WARNING(f"  删除文件失败 {file.name}: {e}")
                        )

            return deleted_count

        except Exception as e:
            self.stdout.write(self.style.WARNING(f"清理旧备份时出错: {e}"))
            return 0
