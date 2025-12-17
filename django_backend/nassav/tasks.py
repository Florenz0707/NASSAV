"""
Celery异步任务定义
"""
from celery import shared_task
from loguru import logger
from django_project.celery import app as celery_app
import redis
from django.conf import settings


def get_redis_client():
    """获取Redis客户端"""
    return redis.from_url(settings.CELERY_BROKER_URL)


def is_task_existed(avid: str):
    """
    检查任务是否已存在于队列中

    Args:
        avid: 视频ID

    Returns:
        bool: 如果任务已存在返回True，否则返回False
    """
    avid = avid.upper()
    task_name = 'nassav.tasks.download_video_task'

    # 检查Redis锁
    redis_client = get_redis_client()
    lock_key = f"nassav:task_lock:{avid}"
    if redis_client.exists(lock_key):
        return True

    # 检查Celery队列中的任务
    insp = celery_app.control.inspect()

    # 检查正在执行的任务
    active_tasks = insp.active() or {}
    for worker, tasks in active_tasks.items():
        for task in tasks:
            if (task.get('name') == task_name and
                task.get('args') and
                len(task['args']) > 0 and
                task['args'][0].upper() == avid):
                return True

    # 检查队列中等待的任务
    scheduled_tasks = insp.scheduled() or {}
    for worker, tasks in scheduled_tasks.items():
        for task in tasks:
            task_info = task.get('request', {})
            if (task_info.get('task') == task_name and
                task_info.get('args') and
                len(task_info['args']) > 0 and
                task_info['args'][0].upper() == avid):
                return True

    # 检查保留的任务（reserved tasks）
    reserved_tasks = insp.reserved() or {}
    for worker, tasks in reserved_tasks.items():
        for task in tasks:
            if (task.get('name') == task_name and
                task.get('args') and
                len(task['args']) > 0 and
                task['args'][0].upper() == avid):
                return True

    return False


def create_task_lock(avid: str, task_id: str, expire_time: int = 3600):
    """
    创建任务锁

    Args:
        avid: 视频ID
        task_id: 任务ID
        expire_time: 锁过期时间（秒）
    """
    redis_client = get_redis_client()
    lock_key = f"nassav:task_lock:{avid.upper()}"
    redis_client.setex(lock_key, expire_time, task_id)


def remove_task_lock(avid: str):
    """
    移除任务锁

    Args:
        avid: 视频ID
    """
    redis_client = get_redis_client()
    lock_key = f"nassav:task_lock:{avid.upper()}"
    redis_client.delete(lock_key)


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

    avid = avid.upper()
    logger.info(f"开始执行下载任务: {avid}, 任务ID: {self.request.id}")

    # 创建任务锁，防止重复执行
    create_task_lock(avid, self.request.id)

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
            remove_task_lock(avid)
            logger.info(f"已清理任务锁: {avid}")
        except Exception as e:
            logger.error(f"清理任务锁失败 {avid}: {str(e)}")


def submit_download_task(avid: str):
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
    if is_task_existed(avid):
        logger.warning(f"任务 {avid} 已存在于队列中，跳过提交")
        return None, True

    # 提交任务
    logger.info(f"提交下载任务: {avid}")
    task_result = download_video_task.delay(avid)

    return task_result, False
