"""
Django management command: 同步备份文件到外部目录

用法：
    python manage.py sync_backups [--target TARGET] [--days DAYS]

参数：
    --target: 目标同步目录（默认：/backup/nassav）
    --days: 只同步最近N天的文件（默认：30天，0表示同步所有）

同步内容：
    - backup/ 目录下的所有备份文件
    - celery_beat/ 目录下的报告文件（celerybeat-schedule除外）
    - log/ 目录下的日志文件
"""
import os
import shutil
from datetime import datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "同步备份文件（backup, celery_beat, log）到指定目录"

    def add_arguments(self, parser):
        parser.add_argument(
            "--target",
            type=str,
            default="/backup/nassav",
            help="目标同步目录（默认：/backup/nassav）",
        )
        parser.add_argument(
            "--days",
            type=int,
            default=30,
            help="只同步最近N天的文件（默认：30天，0表示同步所有）",
        )

    def handle(self, *args, **options):
        target_base = Path(options["target"])
        days = options["days"]

        try:
            # 确保目标目录存在
            target_base.mkdir(parents=True, exist_ok=True)
            self.stdout.write(self.style.SUCCESS(f"目标目录: {target_base}"))

            # 计算时间阈值
            if days > 0:
                cutoff_time = datetime.now() - timedelta(days=days)
                self.stdout.write(
                    f"只同步 {days} 天内的文件（{cutoff_time.strftime('%Y-%m-%d %H:%M:%S')} 之后）"
                )
            else:
                cutoff_time = None
                self.stdout.write("同步所有文件")

            total_synced = 0
            total_size = 0

            # 同步 backup/ 目录
            backup_dir = Path(settings.BASE_DIR) / "backup"
            if backup_dir.exists():
                synced, size = self._sync_directory(
                    backup_dir,
                    target_base / "backup",
                    cutoff_time,
                )
                total_synced += synced
                total_size += size
                self.stdout.write(
                    self.style.SUCCESS(
                        f"✓ 同步 backup/: {synced} 项，{self._format_size(size)}"
                    )
                )
            else:
                self.stdout.write(self.style.WARNING("⚠ backup/ 目录不存在"))

            # 同步 celery_beat/ 目录（排除 celerybeat-schedule）
            celery_beat_dir = Path(settings.BASE_DIR) / "celery_beat"
            if celery_beat_dir.exists():
                synced, size = self._sync_directory(
                    celery_beat_dir,
                    target_base / "celery_beat",
                    cutoff_time,
                    exclude_files=["celerybeat-schedule", "celerybeat-schedule.db"],
                )
                total_synced += synced
                total_size += size
                self.stdout.write(
                    self.style.SUCCESS(
                        f"✓ 同步 celery_beat/: {synced} 项，{self._format_size(size)}"
                    )
                )
            else:
                self.stdout.write(self.style.WARNING("⚠ celery_beat/ 目录不存在"))

            # 同步 celerybeat-schedule（如果存在）
            celerybeat_schedule = Path(settings.BASE_DIR) / "celerybeat-schedule"
            if celerybeat_schedule.exists():
                target_file = target_base / "celerybeat-schedule"
                if self._should_sync_file(celerybeat_schedule, cutoff_time):
                    shutil.copy2(celerybeat_schedule, target_file)
                    file_size = celerybeat_schedule.stat().st_size
                    total_synced += 1
                    total_size += file_size
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"✓ 同步 celerybeat-schedule: {self._format_size(file_size)}"
                        )
                    )

            # 同步 log/ 目录
            log_dir = Path(settings.BASE_DIR) / "log"
            if log_dir.exists():
                synced, size = self._sync_directory(
                    log_dir,
                    target_base / "log",
                    cutoff_time,
                )
                total_synced += synced
                total_size += size
                self.stdout.write(
                    self.style.SUCCESS(
                        f"✓ 同步 log/: {synced} 项，{self._format_size(size)}"
                    )
                )
            else:
                self.stdout.write(self.style.WARNING("⚠ log/ 目录不存在"))

            # 总结
            self.stdout.write(
                self.style.SUCCESS(
                    f"\n{'=' * 60}\n"
                    f"同步完成！\n"
                    f"  - 总共同步: {total_synced} 项\n"
                    f"  - 总大小: {self._format_size(total_size)}\n"
                    f"  - 目标目录: {target_base}\n"
                    f"{'=' * 60}"
                )
            )

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"同步失败: {str(e)}"))
            raise

    def _sync_directory(
        self,
        source_dir: Path,
        target_dir: Path,
        cutoff_time: datetime | None,
        exclude_files: list[str] | None = None,
    ) -> tuple[int, int]:
        """
        同步目录内容

        Args:
            source_dir: 源目录
            target_dir: 目标目录
            cutoff_time: 时间阈值（只同步此时间之后的文件）
            exclude_files: 要排除的文件名列表

        Returns:
            (同步的项数, 总字节数)
        """
        exclude_files = exclude_files or []
        synced_count = 0
        total_size = 0

        # 确保目标目录存在
        target_dir.mkdir(parents=True, exist_ok=True)

        # 遍历源目录
        for item in source_dir.rglob("*"):
            # 跳过目录本身
            if item.is_dir():
                continue

            # 检查是否在排除列表中
            if item.name in exclude_files:
                continue

            # 检查时间过滤
            if not self._should_sync_file(item, cutoff_time):
                continue

            # 计算相对路径
            rel_path = item.relative_to(source_dir)
            target_path = target_dir / rel_path

            # 确保目标子目录存在
            target_path.parent.mkdir(parents=True, exist_ok=True)

            # 复制文件
            shutil.copy2(item, target_path)
            file_size = item.stat().st_size
            synced_count += 1
            total_size += file_size

        return synced_count, total_size

    def _should_sync_file(self, file_path: Path, cutoff_time: datetime | None) -> bool:
        """
        判断文件是否应该被同步

        Args:
            file_path: 文件路径
            cutoff_time: 时间阈值

        Returns:
            是否应该同步
        """
        if cutoff_time is None:
            return True

        # 获取文件的修改时间
        mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
        return mtime >= cutoff_time

    def _format_size(self, size_bytes: int) -> str:
        """
        格式化文件大小

        Args:
            size_bytes: 字节数

        Returns:
            格式化后的字符串（如 "1.5 MB"）
        """
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.2f} PB"
