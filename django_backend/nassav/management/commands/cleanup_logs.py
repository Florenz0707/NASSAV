"""
Django management command: 清理旧日志文件

用法：
    python manage.py cleanup_logs [--days DAYS]

参数：
    --days: 日志文件保留天数（默认：30 天）
"""

from datetime import datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "清理 log/ 目录中过期的日志文件"

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=30,
            help="日志文件保留天数（默认：30）",
        )

    def handle(self, *args, **options):
        days = options.get("days", 30)
        log_dir = Path(settings.BASE_DIR) / "log"

        if not log_dir.exists():
            self.stdout.write(self.style.WARNING("log/ 目录不存在，跳过清理"))
            return

        cutoff_time = None if days <= 0 else datetime.now() - timedelta(days=days)
        self.stdout.write(self.style.SUCCESS(f"开始清理日志目录: {log_dir}"))
        if cutoff_time is None:
            self.stdout.write("保留策略已禁用（days <= 0），不执行删除")
            return

        deleted_count = self.cleanup_old_logs(log_dir, cutoff_time)

        self.stdout.write(self.style.SUCCESS("\n" + "=" * 60))
        self.stdout.write(self.style.SUCCESS("日志清理完成！"))
        if deleted_count > 0:
            self.stdout.write(
                self.style.WARNING(f"已清理 {deleted_count} 个过期日志文件")
            )
        else:
            self.stdout.write("没有发现需要清理的过期日志文件")
        self.stdout.write(f"日志保留策略: 保留最近 {days} 天")
        self.stdout.write(self.style.SUCCESS("=" * 60))

    def cleanup_old_logs(self, log_dir: Path, cutoff_time: datetime) -> int:
        """
        清理过期日志文件，并删除清空后的目录。

        Args:
            log_dir: 日志目录
            cutoff_time: 时间阈值

        Returns:
            删除的文件数量
        """
        deleted_count = 0

        for item in log_dir.rglob("*"):
            if item.is_dir():
                continue

            mtime = datetime.fromtimestamp(item.stat().st_mtime)
            if mtime >= cutoff_time:
                continue

            item.unlink()
            deleted_count += 1
            self.stdout.write(
                self.style.WARNING(f"  已删除过期日志: {item.relative_to(log_dir)}")
            )

        for directory in sorted(
            (path for path in log_dir.rglob("*") if path.is_dir()),
            key=lambda path: len(path.parts),
            reverse=True,
        ):
            if any(directory.iterdir()):
                continue
            directory.rmdir()

        return deleted_count
