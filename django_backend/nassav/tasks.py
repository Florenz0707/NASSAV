"""
Celery异步任务定义
"""

from functools import wraps
from typing import NoReturn, List

from celery import shared_task
from celery.result import AsyncResult
from loguru import logger
from nassav import download_queue
from nassav.download_queue import (
    get_full_task_queue as get_full_task_queue,
    get_task_queue_status as get_task_queue_status,
)
from nassav.download_leases import (
    DownloadLease,
    current_download_ownership,
    download_ownership,
)
from nassav.download_contracts import DownloadLeaseLost


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
def download_video_task(self, avid: str):
    """
    异步下载视频任务

    Args:
        avid: 视频编号

    Returns:
        dict: 下载结果
    """
    from .download_persistence import download_persistence
    from .services import video_download_service
    from .download_workflow import DownloadUseCase
    from nassav.download_contracts import DownloadRetriesExhausted
    from .download_transport import RedisDownloadRuntime

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


def submit_download_task(avid: str) -> tuple[AsyncResult | None, bool]:
    """
    提交下载任务（带去重检查）

    Args:
        avid: 视频ID

    Returns:
        tuple: (task_result, is_duplicate)
            task_result: 任务结果或None
            is_duplicate: 是否为重复任务
    """
    avid = avid.upper()

    # 检查任务是否已存在
    if download_queue.is_task_existed(avid):
        logger.warning(f"任务 {avid} 已存在于队列中，跳过提交")
        return None, True

    # 提交任务
    task_result = download_video_task.delay(avid)

    # 添加到 Redis 队列记录
    download_queue.add_task_to_queue(avid, task_result.id, task_type="download")

    # 发送队列状态更新（使用完整队列）
    download_queue.notify_task_update(
        "queue_status", download_queue.get_full_task_queue()
    )

    return task_result, False


# ============================================================
# 翻译相关任务
# ============================================================


@shared_task(bind=True, name="nassav.tasks.translate_title_task", ignore_result=False)
def translate_title_task(self, avid: str):
    from nassav.composition import build_translation_workflow

    return build_translation_workflow().translate(avid)


@shared_task(
    bind=True, name="nassav.tasks.batch_translate_titles_task", ignore_result=False
)
def batch_translate_titles_task(
    self, avids: List[str] | None = None, skip_existing: bool = True
):
    from nassav.composition import build_translation_workflow

    return build_translation_workflow().translate_batch(avids, skip_existing)


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
    from .download_workflow import MockDownloadUseCase
    from .download_transport import RedisDownloadRuntime

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
from nassav.scrape_jobs import run_resource_job  # noqa: E402, F401
from nassav.search_jobs import run_search_job  # noqa: E402, F401

from nassav.maintenance_tasks import (
    check_videos_consistency as check_videos_consistency,
    check_actor_avatars_consistency as check_actor_avatars_consistency,
    backup_avid_list as backup_avid_list,
    backup_database as backup_database,
    sync_backups as sync_backups,
    cleanup_logs as cleanup_logs,
    check_resources_consistency as check_resources_consistency,
)
