"""
Celery异步任务定义
"""
from celery import shared_task
from loguru import logger


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def download_video_task(self, avid: str):
    """
    异步下载视频任务

    Args:
        avid: 视频编号

    Returns:
        dict: 下载结果
    """
    from .services import video_download_service
    import redis
    from django.conf import settings

    # Redis客户端用于清理队列锁
    redis_client = redis.from_url(settings.CELERY_BROKER_URL)
    task_key = f"nassav:task_queue:{avid.upper()}"

    logger.info(f"开始执行下载任务: {avid}")

    try:
        success = video_download_service.download_video(avid)

        if success:
            logger.info(f"视频 {avid} 下载成功")
            return {
                'status': 'success',
                'avid': avid,
                'message': '下载完成'
            }
        else:
            logger.error(f"视频 {avid} 下载失败")
            return {
                'status': 'failed',
                'avid': avid,
                'message': '下载失败'
            }

    except Exception as e:
        logger.error(f"视频 {avid} 下载异常: {str(e)}")
        # 重试
        try:
            raise self.retry(exc=e)
        except self.MaxRetriesExceededError:
            return {
                'status': 'failed',
                'avid': avid,
                'message': f'下载失败，已达最大重试次数: {str(e)}'
            }
    finally:
        # 任务完成后清理队列锁（无论成功或失败）
        try:
            redis_client.delete(task_key)
            logger.info(f"清理任务队列锁: {avid}")
        except Exception as e:
            logger.warning(f"清理任务队列锁失败 {avid}: {str(e)}")


@shared_task
def batch_download_task(avid_list: list):
    """
    批量下载视频任务

    Args:
        avid_list: 视频编号列表

    Returns:
        dict: 批量下载结果
    """
    from .services import redis_task_queue_lock

    results = []
    for avid in avid_list:
        # 检查是否已有相同任务在队列中
        with redis_task_queue_lock(avid) as can_submit:
            if can_submit:
                result = download_video_task.delay(avid)
                results.append({
                    'avid': avid,
                    'task_id': result.id,
                    'status': 'submitted'
                })
            else:
                results.append({
                    'avid': avid,
                    'task_id': None,
                    'status': 'already_queued'
                })

    return {
        'status': 'processed',
        'tasks': results
    }
