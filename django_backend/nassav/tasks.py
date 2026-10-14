"""
Celery异步任务定义
"""

from functools import wraps
from typing import NoReturn

from celery import shared_task
from loguru import logger
from nassav.task_dispatch import SubmittedTask
from nassav.shared_work_tasks import shared_work_task as shared_work_task

from nassav import download_queue
from nassav.download_contracts import DownloadLeaseLost
from nassav.download_leases import (
    DownloadLease,
    current_download_ownership,
    download_ownership,
)
from nassav.download_queue import (
    get_full_task_queue as get_full_task_queue,
)
from nassav.download_queue import (
    get_task_queue_status as get_task_queue_status,
)


def _owned_download(operation):
    @wraps(operation)
    def execute(task, avid, *args, **kwargs):
        lease = DownloadLease(avid, download_queue.get_redis_client)
        with download_ownership(lease):
            try:
                return operation(task, avid, *args, **kwargs)
            except DownloadLeaseLost as error:
                download_queue.notify_task_update(
                    "task_failed",
                    {
                        "task_id": task.request.id,
                        "avid": avid.upper(),
                        "status": "failed",
                        "message": str(error),
                    },
                )
                return {"status": "failed", "avid": avid.upper(), "message": str(error)}

    return execute


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
@_owned_download
def download_video_task(self, avid: str, job_id: str | None = None):
    """
    异步下载视频任务

    Args:
        avid: 视频编号

    Returns:
        dict: 下载结果
    """
    from nassav.download_contracts import DownloadRetriesExhausted

    if job_id is not None:
        from nassav.composition import build_controlled_download

        return build_controlled_download(current_download_ownership()).run(
            job_id, self.request.id
        )

    from .download_persistence import download_persistence
    from .download_transport import RedisDownloadRuntime
    from .download_workflow import DownloadUseCase
    from .services import video_download_service

    def retry(error: Exception) -> NoReturn:
        try:
            raise self.retry(exc=error)
        except self.MaxRetriesExceededError as exhausted:
            raise DownloadRetriesExhausted() from exhausted

    return DownloadUseCase(
        video_download_service,
        download_persistence,
        RedisDownloadRuntime(),
    ).run(avid, self.request.id, retry=retry, ownership=current_download_ownership())


def submit_download_task(
    avid: str, *, owner_id: int | None = None
) -> tuple[SubmittedTask, bool]:
    """Persist before publishing; paused jobs retain their dedupe reservation.

    owner_id=None is an internal submission, controllable only by an administrator.
    The legacy download task signature remains valid for already published messages.
    """
    from nassav.task_dispatch import submit_download

    return submit_download(avid, owner_id)


# ============================================================
# 翻译相关任务
# ============================================================


@shared_task(
    bind=True,
    name="nassav.tasks.translate_title_task",
    ignore_result=False,
    track_started=True,
)
def translate_title_task(
    self, avid: str, job_id: str | None = None, expected_generation: int | None = None
):
    if job_id is not None:
        from nassav.composition import build_controlled_translation

        return build_controlled_translation().run(job_id, self.request.id)
    from nassav.composition import build_translation_workflow

    versions = (
        {avid.upper(): expected_generation} if expected_generation is not None else None
    )
    return build_translation_workflow(versions).translate(avid)


@shared_task(
    bind=True, name="nassav.tasks.batch_translate_titles_task", ignore_result=False
)
def batch_translate_titles_task(
    self,
    avids: list[str] | None = None,
    skip_existing: bool = True,
    expected_generations: dict[str, int] | None = None,
):
    from nassav.composition import build_translation_workflow

    return build_translation_workflow(expected_generations).translate_batch(
        avids, skip_existing
    )


@shared_task(bind=True)
@_owned_download
def mock_download_video_task(self, avid: str, duration_seconds: int = 30):
    """
    模拟下载视频任务（仅用于测试）

    Args:
        avid: 视频编号
        duration_seconds: 模拟下载持续时间（秒）

    Returns:
        dict: 下载结果
    """
    from time import sleep

    from .download_transport import RedisDownloadRuntime
    from .download_workflow import MockDownloadUseCase

    return MockDownloadUseCase(RedisDownloadRuntime(), sleep).run(
        avid,
        self.request.id,
        duration_seconds=duration_seconds,
        ownership=current_download_ownership(),
    )


def submit_mock_download_task(avid: str, duration_seconds: int = 30):
    """
    提交模拟下载任务（仅用于测试）

    Args:
        avid: 视频编号
        duration_seconds: 模拟下载持续时间（秒）

    Returns:
        tuple: (task_result, is_duplicate)
    """
    avid = avid.upper()

    # 检查任务是否已存在
    if download_queue.is_task_existed(avid):
        logger.warning(f"[测试] 模拟下载任务已存在: {avid}")
        return None, True

    # 提交任务
    try:
        task_result = mock_download_video_task.delay(avid, duration_seconds)
        logger.info(f"[测试] 已提交模拟下载任务: {avid}, task_id={task_result.id}")

        # 添加到 Redis 队列记录
        download_queue.add_task_to_queue(avid, task_result.id, task_type="mock")

        # 发送队列状态更新（使用完整队列）
        download_queue.notify_task_update(
            "queue_status", download_queue.get_full_task_queue()
        )

        return task_result, False
    except Exception as e:
        logger.error(f"[测试] 提交模拟下载任务失败: {avid}, 错误: {e}")
        raise


# Celery autodiscovers tasks.py; import the dedicated scrape task for registration.
from nassav.maintenance_tasks import (
    backup_avid_list as backup_avid_list,
)
from nassav.maintenance_tasks import (
    backup_database as backup_database,
)
from nassav.maintenance_tasks import (
    check_actor_avatars_consistency as check_actor_avatars_consistency,
)
from nassav.maintenance_tasks import (
    check_resources_consistency as check_resources_consistency,
)
from nassav.maintenance_tasks import (
    check_videos_consistency as check_videos_consistency,
)
from nassav.maintenance_tasks import (
    cleanup_logs as cleanup_logs,
)
from nassav.maintenance_tasks import (
    sync_backups as sync_backups,
)
from nassav.scrape_jobs import run_resource_job  # noqa: F401
from nassav.search_jobs import run_search_job  # noqa: F401


@shared_task(
    name="nassav.tasks.recommendation_job_task",
    soft_time_limit=330,
    time_limit=360,
    ignore_result=True,
)
def recommendation_job_task(job_id):
    from nassav.recommendation.jobs import execute

    execute(job_id)


from nassav.maintenance_tasks import cleanup_provider_cache as cleanup_provider_cache


@shared_task(
    name="nassav.tasks.playback_prepare_task",
    soft_time_limit=310,
    time_limit=330,
    ignore_result=True,
)
def playback_prepare_task(session_id):
    from django.conf import settings

    if not settings.PLAYBACK_ENABLED:
        return
    from nassav.composition import build_playback_resolver
    from nassav.playback.preparation import execute
    from nassav.playback import records

    from nassav.composition import build_playback_validator

    resolver = (
        build_playback_resolver(session_id=session_id)
        if settings.SOURCE_CREDENTIALS_ENABLED
        else build_playback_resolver()
    )
    execute(session_id, resolver, records, build_playback_validator())
