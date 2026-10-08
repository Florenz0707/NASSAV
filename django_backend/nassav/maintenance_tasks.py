"""Thin management-command adapters with stable Celery task names."""

from celery import shared_task
from loguru import logger


@shared_task(
    bind=True, name="nassav.tasks.check_videos_consistency", ignore_result=True
)
def check_videos_consistency(
    self,
    apply_changes: bool = False,
    limit: int | None = None,
    report: str | None = None,
):
    """调用管理命令 `check_videos_consistency` 以在 worker 中运行一致性检查（供 Celery Beat 调度）。"""
    try:
        from django.core.management import call_command

        args = []
        if apply_changes:
            args.append("--apply")
        if limit:
            args.extend(["--limit", str(limit)])
        if report:
            args.extend(["--report", report])
        call_command("check_videos_consistency", *args)
    except Exception as e:
        logger.error(f"运行一致性检查任务失败: {e}")


@shared_task(
    bind=True, name="nassav.tasks.check_actor_avatars_consistency", ignore_result=True
)
def check_actor_avatars_consistency(
    self, apply_changes: bool = False, report: str | None = None
):
    """
    检查演员头像一致性（供 Celery Beat 调度）

    Args:
        apply_changes: 如果为True，实际下载缺失的头像；否则只检查不修复
        report: 报告文件路径（JSON格式），如果提供则保存统计结果
    """
    try:
        from django.core.management import call_command

        args = []
        if apply_changes:
            args.append("--apply")
        if report:
            args.extend(["--report", report])
        call_command("check_actor_avatars_consistency", *args)
    except Exception as e:
        logger.error(f"运行演员头像一致性检查任务失败: {e}")


@shared_task(bind=True, name="nassav.tasks.backup_avid_list", ignore_result=True)
def backup_avid_list(self, days: int = 30):
    """
    备份当前数据库中所有 AVID 列表（供 Celery Beat 调度）

    定期保存 AVID 列表到文件，用于灾难恢复场景。
    文件格式：backup/avid_list_{timestamp}.txt
    每行一个 AVID，按字母顺序排列。

    Args:
        days: 备份文件保留天数（默认 30 天）
    """
    try:
        from django.core.management import call_command

        args = ["--days", str(days)]
        call_command("backup_avid_list", *args)
    except Exception as e:
        logger.error(f"备份 AVID 列表失败: {e}")


@shared_task(bind=True, name="nassav.tasks.backup_database", ignore_result=True)
def backup_database(self, days: int = 30):
    """
    备份 SQLite 数据库文件（供 Celery Beat 调度）

    定期备份数据库文件（包含 WAL 和 SHM 文件），用于灾难恢复。
    备份目录：backup/database_{timestamp}/

    Args:
        days: 备份文件保留天数（默认 30 天）
    """
    try:
        from django.core.management import call_command

        args = ["--days", str(days)]
        call_command("backup_database", *args)
    except Exception as e:
        logger.error(f"备份数据库失败: {e}")


@shared_task(bind=True, name="nassav.tasks.sync_backups", ignore_result=True)
def sync_backups(self, target: str | None = None, days: int = 30):
    """
    同步备份文件到外部目录（供 Celery Beat 调度）

    将 backup/, celery_beat/, log/ 目录同步到指定的外部目录。

    Args:
        target: 目标同步目录（默认：/backup/nassav）
        days: 只同步最近N天的文件（默认 30 天，0表示同步所有）
    """
    try:
        from django.core.management import call_command

        args = []
        if target:
            args.extend(["--target", target])
        if days is not None:
            args.extend(["--days", str(days)])

        call_command("sync_backups", *args)
    except Exception as e:
        logger.error(f"同步备份文件失败: {e}")


@shared_task(bind=True, name="nassav.tasks.cleanup_logs", ignore_result=True)
def cleanup_logs(self, days: int = 30):
    """
    清理本地日志目录中的过期文件（供 Celery Beat 调度）

    Args:
        days: 日志文件保留天数（默认 30 天）
    """
    try:
        from django.core.management import call_command

        args = ["--days", str(days)]
        call_command("cleanup_logs", *args)
    except Exception as e:
        logger.error(f"清理日志文件失败: {e}")


@shared_task(
    bind=True, name="nassav.tasks.check_resources_consistency", ignore_result=True
)
def check_resources_consistency(
    self, fix_issues: bool = True, report: str | None = None
):
    """
    检查资源文件与数据库的一致性（供 Celery Beat 调度）

    检查项：
    1. 封面文件存在性（cover_filename 字段与实际文件）
    2. 视频文件存在性（file_exists 字段与实际文件）
    3. 缩略图完整性（如果封面存在，确保三个尺寸的缩略图都存在）

    Args:
        fix_issues: 如果为True，自动修复发现的问题；否则只报告
        report: 报告文件路径（JSON格式），如果提供则保存统计结果
    """
    try:
        from django.core.management import call_command

        args = []
        if fix_issues:
            args.append("--apply")
        if report:
            args.extend(["--report", report])

        call_command("check_resources_consistency", *args)
    except Exception as e:
        logger.error(f"运行资源一致性检查任务失败: {e}")


@shared_task(name="nassav.tasks.cleanup_provider_cache", ignore_result=True)
def cleanup_provider_cache():
    from nassav.resource_cache_maintenance import DjangoProviderCacheMaintenance

    result = DjangoProviderCacheMaintenance().purge(apply=True)
    logger.info("Provider cache cleanup: {}", result)
    return result
