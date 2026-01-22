"""
事件接收器（Signal Receivers）
处理资源相关事件，触发异步任务
"""

from django.dispatch import receiver
from loguru import logger
from nassav.signals import (
    metadata_refreshed,
    resource_added,
    resource_deleted,
    translation_completed,
    video_deleted,
    video_downloaded,
)


@receiver(resource_added)
def on_resource_added(sender, avid, resource, result, **kwargs):
    """
    资源添加完成后的处理
    - 记录日志
    - 可扩展：触发其他异步任务（如生成缩略图）
    """
    logger.info(f"[Event] 资源添加事件触发: {avid}")

    # 注意：翻译任务已在 ResourceService 中直接提交
    # 这里可以添加其他需要异步处理的任务
    # 例如：生成视频缩略图、发送通知等

    # 示例：如果需要生成缩略图（当视频已下载时）
    # if result.get('resource') and result['resource'].file_exists:
    #     from nassav.tasks import generate_thumbnail_task
    #     generate_thumbnail_task.delay(avid)


@receiver(metadata_refreshed)
def on_metadata_refreshed(sender, avid, resource, result, **kwargs):
    """
    元数据刷新完成后的处理
    - 记录日志
    - 可扩展：触发相关更新任务
    """
    logger.info(f"[Event] 元数据刷新事件触发: {avid}")

    # 可以在这里添加元数据刷新后的后续处理
    # 例如：更新搜索索引、清除缓存等


@receiver(resource_deleted)
def on_resource_deleted(sender, avid, delete_files, **kwargs):
    """
    资源删除完成后的处理
    - 记录日志
    - 可扩展：清理相关数据
    """
    logger.info(f"[Event] 资源删除事件触发: {avid}, delete_files={delete_files}")

    # 可以在这里添加资源删除后的清理工作
    # 例如：清除缓存、更新统计数据等


@receiver(video_downloaded)
def on_video_downloaded(sender, avid, **kwargs):
    """
    视频下载完成后的处理
    - 可以触发缩略图生成等任务
    """
    logger.info(f"[Event] 视频下载事件触发: {avid}")

    # 示例：生成视频缩略图
    # from nassav.tasks import generate_thumbnail_task
    # generate_thumbnail_task.delay(avid)


@receiver(video_deleted)
def on_video_deleted(sender, avid, **kwargs):
    """
    视频删除完成后的处理
    """
    logger.info(f"[Event] 视频删除事件触发: {avid}")


@receiver(translation_completed)
def on_translation_completed(sender, avid, translated_title, **kwargs):
    """
    翻译完成后的处理
    - 记录日志
    """
    logger.info(f"[Event] 翻译完成事件触发: {avid}, title={translated_title}")
