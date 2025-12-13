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

    logger.info(f"开始下载视频: {avid}")

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


@shared_task
def batch_download_task(avid_list: list):
    """
    批量下载视频任务

    Args:
        avid_list: 视频编号列表

    Returns:
        dict: 批量下载结果
    """
    results = []
    for avid in avid_list:
        result = download_video_task.delay(avid)
        results.append({
            'avid': avid,
            'task_id': result.id
        })

    return {
        'status': 'submitted',
        'tasks': results
    }
