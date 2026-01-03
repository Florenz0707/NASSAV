"""
Celery异步任务定义
"""
from typing import Any, Dict, List

import redis
from celery import shared_task
from django.conf import settings
from django_project.celery import app as celery_app
from loguru import logger


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
    # 支持真实下载任务和模拟下载任务
    task_names = [
        "nassav.tasks.download_video_task",
        "nassav.tasks.mock_download_video_task",
    ]

    lock_key = f"nassav:task_lock:{avid}"

    # 检查Redis锁（容错）
    try:
        redis_client = get_redis_client()
        try:
            if redis_client.exists(lock_key):
                return True
        except Exception as e:
            logger.error(f"检查 Redis 锁失败: {e}")
    except Exception as e:
        logger.error(f"获取 Redis 客户端失败: {e}")

    # 检查Celery队列中的任务（inspect 可能失败或返回 None）
    try:
        insp = celery_app.control.inspect()
    except Exception as e:
        logger.error(f"获取 Celery inspector 失败: {e}")
        insp = None

    if insp is None:
        # 如果无法检查 Celery 状态，依赖 Redis 锁判断（已检查），无法进一步判断时返回 False
        logger.info("无法获取 Celery inspector，跳过队列检查 (依赖 Redis 锁)。")
        return False

    # 检查正在执行的任务
    try:
        active_tasks = insp.active() or {}
        for worker, tasks in active_tasks.items():
            for task in tasks:
                if (
                    task.get("name") in task_names
                    and task.get("args")
                    and len(task["args"]) > 0
                    and task["args"][0].upper() == avid
                ):
                    return True
    except Exception as e:
        logger.error(f"检查 active 任务失败: {e}")

    # 检查队列中等待的任务
    try:
        scheduled_tasks = insp.scheduled() or {}
        for worker, tasks in scheduled_tasks.items():
            for task in tasks:
                task_info = task.get("request", {})
                if (
                    task_info.get("task") in task_names
                    and task_info.get("args")
                    and len(task_info["args"]) > 0
                    and task_info["args"][0].upper() == avid
                ):
                    return True
    except Exception as e:
        logger.error(f"检查 scheduled 任务失败: {e}")

    # 检查保留的任务（reserved tasks）
    try:
        reserved_tasks = insp.reserved() or {}
        for worker, tasks in reserved_tasks.items():
            for task in tasks:
                if (
                    task.get("name") in task_names
                    and task.get("args")
                    and len(task["args"]) > 0
                    and task["args"][0].upper() == avid
                ):
                    return True
    except Exception as e:
        logger.error(f"检查 reserved 任务失败: {e}")

    return False


def set_task_progress(
    avid: str,
    percent: float,
    speed: str = "N/A",
    eta: str = None,
    downloaded: str = None,
):
    """
    设置任务下载进度

    Args:
        avid: 视频ID
        percent: 下载百分比 (0-100)
        speed: 下载速度字符串
        eta: 预计剩余时间（可选）
        downloaded: 已下载大小（可选）
    """
    redis_client = get_redis_client()
    progress_key = f"nassav:task_progress:{avid.upper()}"
    progress_data = {
        "percent": percent,
        "speed": speed,
        "updated_at": __import__("time").time(),
    }
    if eta is not None:
        progress_data["eta"] = eta
    if downloaded is not None:
        progress_data["downloaded"] = downloaded
    # 设置过期时间为1小时
    redis_client.setex(progress_key, 3600, __import__("json").dumps(progress_data))


def get_task_progress(avid: str) -> Dict[str, Any]:
    """
    获取任务下载进度

    Args:
        avid: 视频ID

    Returns:
        dict: 包含 percent, speed, updated_at 的字典，如果不存在则返回 None
    """
    redis_client = get_redis_client()
    progress_key = f"nassav:task_progress:{avid.upper()}"
    progress_str = redis_client.get(progress_key)
    if progress_str:
        return __import__("json").loads(progress_str)
    return None


def remove_task_progress(avid: str):
    """
    移除任务进度信息

    Args:
        avid: 视频ID
    """
    redis_client = get_redis_client()
    progress_key = f"nassav:task_progress:{avid.upper()}"
    redis_client.delete(progress_key)


def get_task_queue_status() -> Dict[str, Any]:
    """
    获取当前任务队列状态

    Returns:
        dict: 包含活跃任务、等待任务的信息，以及任务计数
    """
    # 支持真实下载任务和模拟下载任务
    task_names = [
        "nassav.tasks.download_video_task",
        "nassav.tasks.mock_download_video_task",
    ]
    insp = celery_app.control.inspect()

    active_tasks_list = []
    pending_tasks_list = []

    # 获取正在执行的任务
    active_tasks = insp.active() or {}
    for worker, tasks in active_tasks.items():
        for task in tasks:
            if (
                task.get("name") in task_names
                and task.get("args")
                and len(task["args"]) > 0
            ):
                avid = task["args"][0].upper()
                task_info = {
                    "task_id": task.get("id"),
                    "avid": avid,
                    "state": "STARTED",
                    "worker": worker,
                    "time_start": task.get("time_start"),
                    "task_type": "mock"
                    if task.get("name") == "nassav.tasks.mock_download_video_task"
                    else "download",
                }
                # 添加进度信息
                progress = get_task_progress(avid)
                if progress:
                    task_info["progress"] = {
                        "percent": progress["percent"],
                        "speed": progress["speed"],
                    }
                active_tasks_list.append(task_info)

    # 获取计划中的任务（pending）
    scheduled_tasks = insp.scheduled() or {}
    for worker, tasks in scheduled_tasks.items():
        for task in tasks:
            task_info = task.get("request", {})
            if (
                task_info.get("task") in task_names
                and task_info.get("args")
                and len(task_info["args"]) > 0
            ):
                pending_tasks_list.append(
                    {
                        "task_id": task_info.get("id"),
                        "avid": task_info["args"][0].upper(),
                        "task_type": "mock"
                        if task_info.get("task")
                        == "nassav.tasks.mock_download_video_task"
                        else "download",
                    }
                )

    # 获取保留的任务（也算 pending）
    reserved_tasks = insp.reserved() or {}
    for worker, tasks in reserved_tasks.items():
        for task in tasks:
            if (
                task.get("name") in task_names
                and task.get("args")
                and len(task["args"]) > 0
            ):
                pending_tasks_list.append(
                    {
                        "task_id": task.get("id"),
                        "avid": task["args"][0].upper(),
                        "task_type": "mock"
                        if task.get("name") == "nassav.tasks.mock_download_video_task"
                        else "download",
                    }
                )

    # 计算统计数据
    active_count = len(active_tasks_list)
    pending_count = len(pending_tasks_list)

    return {
        "active_tasks": active_tasks_list,
        "pending_tasks": pending_tasks_list,
        "active_count": active_count,
        "pending_count": pending_count,
        "total_count": active_count + pending_count,
    }


def notify_task_update(update_type: str, data: dict):
    """
    发送任务更新通知到WebSocket

    Args:
        update_type: 更新类型 ('task_started', 'task_completed', 'task_failed', 'queue_status')
        data: 任务数据
    """
    try:
        from .consumers import send_task_update

        send_task_update(update_type, data)
    except Exception as e:
        logger.error(f"发送任务更新通知失败: {str(e)}")


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


def add_task_to_queue(avid: str, task_id: str, task_type: str = "download"):
    """
    添加任务到 Redis 队列记录（用于追踪完整任务列表）

    Args:
        avid: 视频ID
        task_id: 任务ID
        task_type: 任务类型（'download' 或 'mock'）
    """
    import time

    redis_client = get_redis_client()
    queue_key = "nassav:task_queue"
    task_data = {
        "task_id": task_id,
        "avid": avid.upper(),
        "state": "PENDING",
        "task_type": task_type,
        "created_at": time.time(),
    }
    # 使用 HSET 存储，key 为 avid，value 为任务数据 JSON
    redis_client.hset(queue_key, avid.upper(), __import__("json").dumps(task_data))
    # 设置整个 hash 的过期时间（24小时）
    redis_client.expire(queue_key, 86400)


def update_task_state_in_queue(avid: str, state: str):
    """
    更新队列中任务的状态

    Args:
        avid: 视频ID
        state: 任务状态（'PENDING', 'STARTED', 'SUCCESS', 'FAILURE'）
    """
    redis_client = get_redis_client()
    queue_key = "nassav:task_queue"
    avid_upper = avid.upper()

    # 获取现有任务数据
    task_data_str = redis_client.hget(queue_key, avid_upper)
    if task_data_str:
        task_data = __import__("json").loads(task_data_str)
        task_data["state"] = state
        task_data["updated_at"] = __import__("time").time()
        redis_client.hset(queue_key, avid_upper, __import__("json").dumps(task_data))


def remove_task_from_queue(avid: str):
    """
    从 Redis 队列记录中移除任务

    Args:
        avid: 视频ID
    """
    redis_client = get_redis_client()
    queue_key = "nassav:task_queue"
    redis_client.hdel(queue_key, avid.upper())


def get_full_task_queue() -> Dict[str, Any]:
    """
    从 Redis 获取完整任务队列（包括所有 pending 和 active 任务）

    Returns:
        dict: 包含完整任务列表的字典
    """
    redis_client = get_redis_client()
    queue_key = "nassav:task_queue"

    try:
        all_tasks_data = redis_client.hgetall(queue_key)

        if not all_tasks_data:
            return {
                "active_tasks": [],
                "pending_tasks": [],
                "active_count": 0,
                "pending_count": 0,
                "total_count": 0,
            }

        # 解析任务数据
        all_tasks = []
        for task_json in all_tasks_data.values():
            try:
                task = __import__("json").loads(task_json)

                # 为每个任务添加进度信息（如果有）
                progress = get_task_progress(task["avid"])
                if progress:
                    # 包含所有可用的进度字段
                    task["progress"] = progress

                all_tasks.append(task)
            except Exception as e:
                logger.error(f"解析任务数据失败: {e}")
                continue

        # 按状态分类
        active_tasks = [t for t in all_tasks if t.get("state") == "STARTED"]
        pending_tasks = [t for t in all_tasks if t.get("state") == "PENDING"]

        # 按创建时间排序
        active_tasks.sort(key=lambda x: x.get("created_at", 0))
        pending_tasks.sort(key=lambda x: x.get("created_at", 0))

        return {
            "active_tasks": active_tasks,
            "pending_tasks": pending_tasks,
            "active_count": len(active_tasks),
            "pending_count": len(pending_tasks),
            "total_count": len(all_tasks),
        }
    except Exception as e:
        logger.error(f"获取完整任务队列失败: {e}")
        # 如果 Redis 队列失败，回退到原来的 Celery inspector 方法
        return get_task_queue_status()


def remove_task_lock(avid: str):
    """
    移除任务锁

    Args:
        avid: 视频ID
    """
    redis_client = get_redis_client()
    lock_key = f"nassav:task_lock:{avid.upper()}"
    redis_client.delete(lock_key)


def acquire_global_download_lock(timeout: int = 3600):
    """
    获取全局下载锁，确保同一时间只有一个下载任务在执行

    Args:
        timeout: 锁超时时间（秒）

    Returns:
        bool: 成功获取锁返回True，否则返回False
    """
    redis_client = get_redis_client()
    lock_key = "nassav:global_download_lock"
    # 使用 set nx ex 原子操作获取锁
    return redis_client.set(lock_key, "locked", nx=True, ex=timeout)


def release_global_download_lock():
    """
    释放全局下载锁
    """
    redis_client = get_redis_client()
    lock_key = "nassav:global_download_lock"
    redis_client.delete(lock_key)


def wait_for_global_download_lock(max_wait_time: int = 600, check_interval: int = 5):
    """
    等待获取全局下载锁

    Args:
        max_wait_time: 最大等待时间（秒）
        check_interval: 检查间隔（秒）

    Returns:
        bool: 成功获取锁返回True，超时返回False
    """
    import time

    elapsed = 0
    while elapsed < max_wait_time:
        if acquire_global_download_lock():
            return True
        time.sleep(check_interval)
        elapsed += check_interval
    logger.warning(f"等待全局下载锁超时: {max_wait_time}秒")
    return False


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

    # 等待并获取全局下载锁，确保同一时间只有一个下载任务在执行
    if not wait_for_global_download_lock(max_wait_time=1800):  # 最多等待30分钟
        logger.error(f"获取全局下载锁超时: {avid}")
        remove_task_lock(avid)
        remove_task_from_queue(avid)

        # 发送任务失败通知
        notify_task_update(
            "task_failed",
            {
                "task_id": self.request.id,
                "avid": avid,
                "status": "failed",
                "message": "获取下载锁超时，可能有其他下载任务正在执行",
            },
        )
        notify_task_update("queue_status", get_full_task_queue())

        return {"status": "failed", "avid": avid, "message": "获取下载锁超时，可能有其他下载任务正在执行"}

    # 更新 Redis 队列中的任务状态为 STARTED
    update_task_state_in_queue(avid, "STARTED")

    # 发送任务开始通知
    notify_task_update(
        "task_started", {"task_id": self.request.id, "avid": avid, "status": "started"}
    )

    # 发送更新后的队列状态（使用完整队列）
    notify_task_update("queue_status", get_full_task_queue())

    # 创建节流器，限制 WebSocket 通知频率（每秒最多1次）
    from nassav.utils import Throttler

    ws_throttler = Throttler(min_interval=1.0)

    # 定义进度回调函数
    def progress_callback(percent: float, speed: str, eta: str):
        """更新下载进度并通知 WebSocket（带节流）"""
        # Redis 进度更新保持原频率（供 API 查询）
        set_task_progress(avid, percent, speed, eta=eta)

        # WebSocket 通知使用节流：100% 时强制发送
        if ws_throttler.should_execute(force=(percent >= 100)):
            notify_task_update(
                "progress_update",
                {
                    "task_id": self.request.id,
                    "avid": avid,
                    "percent": percent,
                    "speed": speed,
                    "eta": eta,
                },
            )

    try:
        success = video_download_service.download_video(
            avid, progress_callback=progress_callback
        )

        if success:
            # 从 Redis 队列中移除任务
            remove_task_from_queue(avid)

            # 发送任务完成通知
            notify_task_update(
                "task_completed",
                {
                    "task_id": self.request.id,
                    "avid": avid,
                    "status": "success",
                    "message": "下载完成",
                },
            )
            notify_task_update("queue_status", get_full_task_queue())

            # 更新数据库：标记文件存在并写入文件大小/时间戳
            try:
                from pathlib import Path

                from django.conf import settings
                from django.db import transaction
                from django.utils import timezone
                from nassav.models import AVResource

                mp4_file = Path(settings.VIDEO_DIR) / f"{avid.upper()}.mp4"
                with transaction.atomic():
                    if mp4_file.exists():
                        file_size = mp4_file.stat().st_size
                        AVResource.objects.filter(avid=avid).update(
                            file_exists=True,
                            file_size=file_size,
                            video_saved_at=timezone.now(),
                        )
                    else:
                        AVResource.objects.filter(avid=avid).update(
                            file_exists=False, file_size=None, video_saved_at=None
                        )
            except Exception as e:
                logger.warning(f"下载完成后更新 AVResource 失败: {e}")

            return {"status": "success", "avid": avid, "message": "下载完成"}
        else:
            logger.error(f"视频 {avid} 下载失败")

            # 从 Redis 队列中移除任务
            remove_task_from_queue(avid)

            # 发送任务失败通知
            notify_task_update(
                "task_failed",
                {
                    "task_id": self.request.id,
                    "avid": avid,
                    "status": "failed",
                    "message": "下载失败",
                },
            )
            notify_task_update("queue_status", get_full_task_queue())

            # 标记数据库为未完成
            try:
                from django.db import transaction
                from nassav.models import AVResource

                with transaction.atomic():
                    AVResource.objects.filter(avid=avid).update(file_exists=False)
            except Exception as e:
                logger.warning(f"下载失败后更新 AVResource 失败: {e}")

            return {"status": "failed", "avid": avid, "message": "下载失败"}

    except Exception as e:
        logger.error(f"视频 {avid} 下载异常: {str(e)}")

        # 从 Redis 队列中移除任务
        remove_task_from_queue(avid)

        # 发送任务失败通知
        notify_task_update(
            "task_failed",
            {
                "task_id": self.request.id,
                "avid": avid,
                "status": "failed",
                "message": f"下载异常: {str(e)}",
            },
        )
        notify_task_update("queue_status", get_full_task_queue())

        # 重试
        try:
            raise self.retry(exc=e)
        except self.MaxRetriesExceededError:
            try:
                from django.db import transaction
                from nassav.models import AVResource

                with transaction.atomic():
                    AVResource.objects.filter(avid=avid).update(file_exists=False)
            except Exception as e:
                logger.warning(f"重试出现异常：{str(e)}")
            return {
                "status": "failed",
                "avid": avid,
                "message": f"下载失败，已达最大重试次数: {str(e)}",
            }
    finally:
        # 任务完成后清理队列锁和全局下载锁（无论成功或失败）
        try:
            release_global_download_lock()
            logger.info(f"已释放全局下载锁: {avid}")
        except Exception as e:
            logger.error(f"释放全局下载锁失败 {avid}: {str(e)}")

        try:
            remove_task_lock(avid)
            logger.info(f"已清理任务锁: {avid}")
        except Exception as e:
            logger.error(f"清理任务锁失败 {avid}: {str(e)}")

        # 清理进度信息
        try:
            remove_task_progress(avid)
            logger.info(f"已清理任务进度: {avid}")
        except Exception as e:
            logger.error(f"清理任务进度失败 {avid}: {str(e)}")

        # 发送最终队列状态
        notify_task_update("queue_status", get_full_task_queue())


def submit_download_task(avid: str) -> tuple[bool | None, bool]:
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
    task_result = download_video_task.delay(avid)

    # 添加到 Redis 队列记录
    add_task_to_queue(avid, task_result.id, task_type="download")

    # 发送队列状态更新（使用完整队列）
    notify_task_update("queue_status", get_full_task_queue())

    return task_result, False


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


# ============================================================
# 翻译相关任务
# ============================================================


@shared_task(bind=True, name="nassav.tasks.translate_title_task", ignore_result=False)
def translate_title_task(self, avid: str):
    """
    异步翻译资源标题任务

    Args:
        avid: 资源 AVID

    Returns:
        dict: 包含翻译结果的字典
    """
    avid = avid.upper()
    logger.info(f"[翻译任务] 开始翻译 {avid} 的标题")

    try:
        from nassav.models import AVResource
        from nassav.translator import translator_manager

        # 获取资源
        resource = AVResource.objects.filter(avid=avid).first()
        if not resource:
            logger.warning(f"[翻译任务] 资源 {avid} 不存在")
            return {"success": False, "error": f"资源 {avid} 不存在", "avid": avid}

        # 检查是否已有翻译
        if resource.translated_title and resource.translation_status == "completed":
            return {
                "success": True,
                "skipped": True,
                "avid": avid,
                "translation_status": "completed",
                "translated_title": resource.translated_title,
            }

        # 获取待翻译的标题
        title_to_translate = resource.original_title or resource.source_title
        if not title_to_translate:
            logger.warning(f"[翻译任务] {avid} 没有可翻译的标题")
            resource.translation_status = "skipped"
            resource.save(update_fields=["translation_status"])
            return {
                "success": False,
                "error": "没有可翻译的标题",
                "avid": avid,
                "translation_status": "skipped",
            }

        # 更新状态为翻译中
        resource.translation_status = "translating"
        resource.save(update_fields=["translation_status"])

        # 执行翻译
        translated = translator_manager.translate(title_to_translate)

        if translated:
            resource.translated_title = translated
            resource.translation_status = "completed"
            resource.save(update_fields=["translated_title", "translation_status"])
            logger.info(
                f"[翻译任务] {avid} 翻译成功\n 原文：{title_to_translate}\n 翻译：{translated}"
            )

            return {
                "success": True,
                "avid": avid,
                "translation_status": "completed",
                "original": title_to_translate,
                "translated_title": translated,
            }
        else:
            resource.translation_status = "failed"
            resource.save(update_fields=["translation_status"])
            logger.warning(f"[翻译任务] {avid} 翻译返回空结果")
            return {
                "success": False,
                "error": "翻译返回空结果",
                "avid": avid,
                "translation_status": "failed",
            }

    except Exception as e:
        logger.error(f"[翻译任务] {avid} 翻译失败: {e}")
        # 尝试更新状态为失败
        try:
            from nassav.models import AVResource

            resource = AVResource.objects.filter(avid=avid).first()
            if resource:
                resource.translation_status = "failed"
                resource.save(update_fields=["translation_status"])
        except Exception:
            pass
        return {
            "success": False,
            "error": str(e),
            "avid": avid,
            "translation_status": "failed",
        }


@shared_task(
    bind=True, name="nassav.tasks.batch_translate_titles_task", ignore_result=False
)
def batch_translate_titles_task(
    self, avids: List[str] = None, skip_existing: bool = True
):
    """
    批量翻译资源标题任务

    Args:
        avids: 要翻译的 AVID 列表，为空则翻译所有未翻译的
        skip_existing: 是否跳过已有翻译的记录

    Returns:
        dict: 包含批量翻译结果的统计
    """
    logger.info(f"[批量翻译任务] 开始批量翻译")

    try:
        from django.db.models import Q
        from nassav.models import AVResource
        from nassav.translator import translator_manager

        # 构建查询
        if avids:
            avids = [a.upper() for a in avids]
            query = Q(avid__in=avids)
        else:
            query = Q()

        # 只翻译有标题的记录
        query &= (Q(title__isnull=False) & ~Q(title="")) | (
            Q(source_title__isnull=False) & ~Q(source_title="")
        )

        if skip_existing:
            # 跳过已完成的翻译
            query &= ~Q(translation_status="completed")

        resources = AVResource.objects.filter(query)
        total = resources.count()

        if total == 0:
            logger.info("[批量翻译任务] 没有需要翻译的记录")
            return {
                "success": True,
                "total": 0,
                "translated": 0,
                "failed": 0,
                "skipped": 0,
            }

        logger.info(f"[批量翻译任务] 需要翻译 {total} 条记录")

        # 批量更新状态为翻译中
        resources.update(translation_status="translating")

        # 准备翻译文本
        texts = []
        resource_list = list(AVResource.objects.filter(query))  # 重新获取
        for r in resource_list:
            texts.append(r.original_title or r.source_title or "")

        # 批量翻译
        results = translator_manager.batch_translate(texts)

        # 保存结果
        translated_count = 0
        failed_count = 0
        skipped_count = 0

        for idx, translation in enumerate(results):
            resource = resource_list[idx]
            if not (resource.original_title or resource.source_title):
                resource.translation_status = "skipped"
                resource.save(update_fields=["translation_status"])
                skipped_count += 1
            elif translation:
                resource.translated_title = translation
                resource.translation_status = "completed"
                resource.save(update_fields=["translated_title", "translation_status"])
                translated_count += 1
            else:
                resource.translation_status = "failed"
                resource.save(update_fields=["translation_status"])
                failed_count += 1

        logger.info(
            f"[批量翻译任务] 完成: 成功 {translated_count}, 失败 {failed_count}, 跳过 {skipped_count}"
        )

        return {
            "success": True,
            "total": total,
            "translated": translated_count,
            "failed": failed_count,
            "skipped": skipped_count,
        }

    except Exception as e:
        logger.error(f"[批量翻译任务] 失败: {e}")
        return {"success": False, "error": str(e)}


def submit_translate_task(avid: str, async_mode: bool = True):
    """
    提交翻译任务的辅助函数

    Args:
        avid: 资源 AVID
        async_mode: 是否异步执行（True=Celery异步, False=同步执行）

    Returns:
        tuple: (task_result, is_async)
    """
    avid = avid.upper()

    if async_mode:
        try:
            task_result = translate_title_task.delay(avid)
            logger.info(f"已提交异步翻译任务: {avid}, task_id={task_result.id}")
            return task_result, True
        except Exception as e:
            logger.warning(f"提交异步翻译任务失败，回退到同步模式: {e}")
            # 回退到同步模式
            result = translate_title_task(avid)
            return result, False
    else:
        result = translate_title_task(avid)
        return result, False


@shared_task(bind=True)
def mock_download_video_task(self, avid: str, duration_seconds: int = 30):
    """
    模拟下载视频任务（仅用于测试）

    Args:
        avid: 视频编号
        duration_seconds: 模拟下载持续时间（秒）

    Returns:
        dict: 下载结果
    """
    import time

    avid = avid.upper()
    logger.info(
        f"[测试] 开始模拟下载任务: {avid}, 任务ID: {self.request.id}, 持续时间: {duration_seconds}秒"
    )

    # 创建任务锁
    create_task_lock(avid, self.request.id)

    # 更新 Redis 队列中的任务状态为 STARTED
    update_task_state_in_queue(avid, "STARTED")

    # 发送任务开始通知
    notify_task_update(
        "task_started", {"task_id": self.request.id, "avid": avid, "status": "started"}
    )

    # 发送更新后的队列状态
    notify_task_update("queue_status", get_full_task_queue())

    try:
        # 模拟下载过程，每秒更新进度
        step = 100.0 / duration_seconds
        for i in range(duration_seconds):
            time.sleep(1)
            percent = min(100.0, (i + 1) * step)
            speed = f"{((i + 1) * 2):.1f} MB/s"  # 模拟速度
            remaining = duration_seconds - (i + 1)
            eta = (
                f"00:00:{remaining:02d}"
                if remaining < 60
                else f"00:{remaining // 60:02d}:{remaining % 60:02d}"
            )

            # 更新进度
            set_task_progress(avid, percent, speed, eta=eta)

            # 发送进度通知
            notify_task_update(
                "progress_update",
                {
                    "task_id": self.request.id,
                    "avid": avid,
                    "percent": percent,
                    "speed": speed,
                    "eta": eta,
                },
            )

            logger.debug(f"[测试] {avid} 下载进度: {percent:.1f}%")

        # 模拟下载完成
        logger.info(f"[测试] 模拟下载完成: {avid}")

        # 清理进度和锁
        remove_task_progress(avid)
        remove_task_lock(avid)

        # 从 Redis 队列中移除任务
        remove_task_from_queue(avid)

        # 发送任务完成通知
        notify_task_update(
            "task_completed",
            {
                "task_id": self.request.id,
                "avid": avid,
                "status": "completed",
                "message": "模拟下载完成",
            },
        )

        # 发送更新后的队列状态
        notify_task_update("queue_status", get_full_task_queue())

        return {
            "status": "completed",
            "avid": avid,
            "task_id": self.request.id,
            "message": "模拟下载完成",
        }

    except Exception as e:
        logger.error(f"[测试] 模拟下载失败: {avid}, 错误: {e}")

        # 清理
        remove_task_progress(avid)
        remove_task_lock(avid)

        # 从 Redis 队列中移除任务
        remove_task_from_queue(avid)

        # 发送任务失败通知
        notify_task_update(
            "task_failed",
            {
                "task_id": self.request.id,
                "avid": avid,
                "status": "failed",
                "message": f"模拟下载失败: {str(e)}",
            },
        )

        # 发送更新后的队列状态
        notify_task_update("queue_status", get_full_task_queue())

        return {
            "status": "failed",
            "avid": avid,
            "task_id": self.request.id,
            "error": str(e),
        }


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
    if is_task_existed(avid):
        logger.warning(f"[测试] 模拟下载任务已存在: {avid}")
        return None, True

    # 提交任务
    try:
        task_result = mock_download_video_task.delay(avid, duration_seconds)
        logger.info(f"[测试] 已提交模拟下载任务: {avid}, task_id={task_result.id}")

        # 添加到 Redis 队列记录
        add_task_to_queue(avid, task_result.id, task_type="mock")

        # 发送队列状态更新（使用完整队列）
        notify_task_update("queue_status", get_full_task_queue())

        return task_result, False
    except Exception as e:
        logger.error(f"[测试] 提交模拟下载任务失败: {avid}, 错误: {e}")
        raise


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
