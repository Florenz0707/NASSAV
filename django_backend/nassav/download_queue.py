"""Redis queue, progress, ownership and Channels event transport."""

from typing import Any

import redis
from django.conf import settings
from django_project.celery import app as celery_app
from loguru import logger

from nassav.download_contracts import DownloadLeaseLost
from nassav.download_leases import current_download_ownership


def get_redis_client() -> redis.Redis:  # type: ignore
    """获取Redis客户端"""
    return redis.from_url(
        settings.CELERY_BROKER_URL, socket_connect_timeout=2, socket_timeout=2
    )


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
    eta: str | None = None,
    downloaded: str | None = None,
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
    lease = current_download_ownership()
    if lease is not None:
        if not lease.mutate("progress", __import__("json").dumps(progress_data)):
            raise DownloadLeaseLost("下载进度写入时租约已丢失")
        return
    # 设置过期时间为1小时
    redis_client.setex(progress_key, 3600, __import__("json").dumps(progress_data))


def get_task_progress(avid: str) -> dict[str, Any] | None:
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
    lease = current_download_ownership()
    if lease is not None:
        lease.mutate("remove_progress", "")
        return
    redis_client = get_redis_client()
    progress_key = f"nassav:task_progress:{avid.upper()}"
    redis_client.delete(progress_key)


def get_task_queue_status() -> dict[str, Any]:
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
                    if "downloaded" in progress:
                        task_info["progress"]["downloaded"] = progress["downloaded"]
                    if "total" in progress:
                        task_info["progress"]["total"] = progress["total"]
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
        logger.error(f"发送任务更新通知失败: {e!s}")


def create_task_lock(avid: str, task_id: str, expire_time: int = 3600):
    """
    创建任务锁

    Args:
        avid: 视频ID
        task_id: 任务ID
        expire_time: 锁过期时间（秒）
    """
    lease = current_download_ownership()
    if lease is None:
        raise RuntimeError("Task locks require an execution ownership context")
    lease.start(expire_time)


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
    lease = current_download_ownership()
    if lease is not None:
        if not lease.mutate("state", state):
            raise DownloadLeaseLost("下载状态写入时租约已丢失")
        return
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
    lease = current_download_ownership()
    if lease is not None:
        lease.mutate("remove_queue", "")
        return
    redis_client = get_redis_client()
    queue_key = "nassav:task_queue"
    redis_client.hdel(queue_key, avid.upper())


def get_full_task_queue() -> dict[str, Any]:
    """
    从 Redis 获取完整任务队列（包括所有 pending 和 active 任务）

    Returns:
        dict: 包含完整任务列表的字典
    """
    redis_client = get_redis_client()
    queue_key = "nassav:task_queue"

    try:
        all_tasks_data: dict[bytes, bytes] = redis_client.hgetall(queue_key)  # type: ignore

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
    lease = current_download_ownership()
    if lease is not None:
        lease.mutate("cleanup", "")
        return
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
    lease = current_download_ownership()
    if lease is None:
        raise RuntimeError("Global downloads require an execution ownership context")
    return lease.acquire_global(timeout)


def release_global_download_lock():
    lease = current_download_ownership()
    return lease.release_global() if lease is not None else False


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
