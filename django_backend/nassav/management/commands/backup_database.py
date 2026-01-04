"""
Django management command: 备份 SQLite 数据库（包含 WAL 文件）

用法：
    python manage.py backup_database [--days DAYS]

参数：
    --days: 备份文件保留天数（默认：30 天）

备份内容：
    - db.sqlite3（主数据库文件）
    - db.sqlite3-wal（Write-Ahead Log）
    - db.sqlite3-shm（Shared Memory）
"""
import shutil
import time
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "备份 SQLite 数据库文件（包含 WAL 和 SHM 文件）"

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=30,
            help="备份文件保留天数（默认：30）",
        )

    def handle(self, *args, **options):
        days = options.get("days", 30)

        try:
            # 创建备份目录
            backup_base_dir = Path(settings.BASE_DIR) / "backup"
            backup_base_dir.mkdir(parents=True, exist_ok=True)

            self.stdout.write(self.style.SUCCESS("开始备份数据库..."))

            # 生成时间戳
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_dir = backup_base_dir / f"database_{timestamp}"
            backup_dir.mkdir(parents=True, exist_ok=True)

            # 获取数据库文件路径
            db_path = Path(settings.DATABASES["default"]["NAME"])

            if not db_path.exists():
                self.stdout.write(self.style.ERROR(f"数据库文件不存在: {db_path}"))
                return

            # 步骤 1: 触发 WAL 检查点，确保数据同步
            self.stdout.write("  触发 WAL 检查点...")
            try:
                cursor = connection.cursor()
                cursor.execute("PRAGMA wal_checkpoint(FULL)")
                result = cursor.fetchall()
                self.stdout.write(self.style.SUCCESS(f"  检查点完成: {result}"))
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"  触发检查点失败（可能未启用 WAL）: {e}"))

            # 步骤 2: 复制主数据库文件
            self.stdout.write("  复制主数据库文件...")
            db_backup = backup_dir / "db.sqlite3"
            shutil.copy2(db_path, db_backup)
            db_size = db_backup.stat().st_size / (1024 * 1024)  # MB
            self.stdout.write(
                self.style.SUCCESS(f"  已复制: db.sqlite3 ({db_size:.2f} MB)")
            )

            # 步骤 3: 复制 WAL 和 SHM 文件（如果存在）
            wal_copied = False
            shm_copied = False

            for suffix in ["-wal", "-shm"]:
                src_file = Path(str(db_path) + suffix)
                if src_file.exists():
                    dst_file = backup_dir / f"db.sqlite3{suffix}"
                    shutil.copy2(src_file, dst_file)
                    file_size = dst_file.stat().st_size / 1024  # KB
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"  已复制: db.sqlite3{suffix} ({file_size:.2f} KB)"
                        )
                    )
                    if suffix == "-wal":
                        wal_copied = True
                    elif suffix == "-shm":
                        shm_copied = True
                else:
                    self.stdout.write(
                        self.style.WARNING(f"  跳过: db.sqlite3{suffix} (文件不存在)")
                    )

            # 步骤 4: 创建备份元信息
            meta_file = backup_dir / "backup_info.txt"
            with open(meta_file, "w", encoding="utf-8") as f:
                f.write(f"备份时间: {datetime.now().isoformat()}\n")
                f.write(f"数据库路径: {db_path}\n")
                f.write(f"主数据库大小: {db_size:.2f} MB\n")
                f.write(f"WAL 文件: {'存在' if wal_copied else '不存在'}\n")
                f.write(f"SHM 文件: {'存在' if shm_copied else '不存在'}\n")

            # 步骤 5: 清理旧备份
            deleted_count = self.cleanup_old_backups(backup_base_dir, days)

            # 输出统计
            self.stdout.write(self.style.SUCCESS("\n" + "=" * 60))
            self.stdout.write(self.style.SUCCESS("数据库备份完成！"))
            self.stdout.write(f"备份目录: {backup_dir}")
            self.stdout.write(f"主数据库: {db_size:.2f} MB")
            self.stdout.write(f"WAL 模式: {'已启用' if wal_copied else '未启用'}")
            if deleted_count > 0:
                self.stdout.write(self.style.WARNING(f"已清理 {deleted_count} 个旧备份"))
            self.stdout.write(f"备份保留策略: 保留最近 {days} 天")
            self.stdout.write(self.style.SUCCESS("=" * 60))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"备份失败: {e}"))
            raise

    def cleanup_old_backups(self, backup_dir: Path, days: int = 30) -> int:
        """
        清理旧的数据库备份

        Args:
            backup_dir: 备份根目录
            days: 保留天数

        Returns:
            删除的备份目录数量
        """
        try:
            cutoff_time = time.time() - (days * 86400)
            deleted_count = 0

            # 查找所有备份目录
            for item in backup_dir.glob("database_*"):
                if item.is_dir() and item.stat().st_mtime < cutoff_time:
                    try:
                        shutil.rmtree(item)
                        deleted_count += 1
                        self.stdout.write(self.style.WARNING(f"  已删除旧备份: {item.name}"))
                    except Exception as e:
                        self.stdout.write(
                            self.style.WARNING(f"  删除备份失败 {item.name}: {e}")
                        )

            return deleted_count

        except Exception as e:
            self.stdout.write(self.style.WARNING(f"清理旧备份时出错: {e}"))
            return 0
