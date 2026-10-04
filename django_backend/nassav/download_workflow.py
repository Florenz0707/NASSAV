"""Download orchestration independent of Celery task objects and Redis clients."""

from nassav.download_contracts import (
    DownloadRetriesExhausted,
    DownloadRuntime,
    DownloadWorkflow,
)

from collections.abc import Callable
from typing import NoReturn
from loguru import logger
from nassav.download_contracts import DownloadOwnership, DownloadLeaseLost
from nassav.download_contracts import DownloadExecutor
from nassav.download_contracts import DownloadPersistence


class DownloadUseCase(DownloadWorkflow):
    def __init__(
        self,
        executor: DownloadExecutor,
        persistence: DownloadPersistence,
        runtime: DownloadRuntime,
    ):
        self.executor, self.persistence, self.runtime = executor, persistence, runtime

    def run(
        self,
        avid: str,
        task_id: str,
        *,
        retry: Callable[[Exception], NoReturn],
        ownership: DownloadOwnership | None = None,
    ) -> dict:
        runtime = self.runtime
        avid = avid.upper()
        logger.info(f"开始执行下载任务: {avid}, 任务ID: {task_id}")

        # 创建任务锁，防止重复执行
        runtime.create_lock(avid, task_id)

        # 等待并获取全局下载锁，确保同一时间只有一个下载任务在执行
        if not runtime.wait_for_slot(max_wait_time=1800):  # 最多等待30分钟
            logger.error(f"获取全局下载锁超时: {avid}")
            runtime.remove_lock(avid)
            runtime.remove_from_queue(avid)

            # 发送任务失败通知
            runtime.notify(
                "task_failed",
                {
                    "task_id": task_id,
                    "avid": avid,
                    "status": "failed",
                    "message": "获取下载锁超时，可能有其他下载任务正在执行",
                },
            )
            runtime.notify("queue_status", runtime.queue_status())

            return {
                "status": "failed",
                "avid": avid,
                "message": "获取下载锁超时，可能有其他下载任务正在执行",
            }

        # 更新 Redis 队列中的任务状态为 STARTED
        runtime.set_state(avid, "STARTED")

        # 发送任务开始通知
        runtime.notify(
            "task_started", {"task_id": task_id, "avid": avid, "status": "started"}
        )

        # 发送更新后的队列状态（使用完整队列）
        runtime.notify("queue_status", runtime.queue_status())

        # 创建节流器，限制 WebSocket 通知频率（每秒最多1次）
        from nassav.utils import Throttler

        ws_throttler = Throttler(min_interval=1.0)

        # 定义进度回调函数
        def progress_callback(percent: float, speed: str, eta: str):
            """更新下载进度并通知 WebSocket（带节流）"""

            if ownership:
                ownership.check()
            # Redis 进度更新保持原频率（供 API 查询）
            runtime.set_progress(avid, percent, speed, eta=eta)

            # WebSocket 通知使用节流：100% 时强制发送
            if ws_throttler.should_execute(force=(percent >= 100)):
                runtime.notify(
                    "progress_update",
                    {
                        "task_id": task_id,
                        "avid": avid,
                        "percent": percent,
                        "speed": speed,
                        "eta": eta,
                    },
                )

        try:
            success = self.executor.download_video(
                avid,
                progress_callback=progress_callback,
                cancelled=ownership.cancelled if ownership else None,
            )

            if ownership:
                ownership.check()
            if success:
                # 从 Redis 队列中移除任务
                runtime.remove_from_queue(avid)

                # 发送任务完成通知
                runtime.notify(
                    "task_completed",
                    {
                        "task_id": task_id,
                        "avid": avid,
                        "status": "success",
                        "message": "下载完成",
                    },
                )
                runtime.notify("queue_status", runtime.queue_status())

                # 文件元数据由持久化适配器更新，任务仅编排队列与通知。
                try:
                    if ownership:
                        ownership.check()
                    self.persistence.mark_completed(avid)
                except DownloadLeaseLost:
                    raise
                except Exception as e:
                    logger.warning(f"下载完成后更新 AVResource 失败: {e}")

                return {"status": "success", "avid": avid, "message": "下载完成"}
            else:
                logger.error(f"视频 {avid} 下载失败")

                # 从 Redis 队列中移除任务
                runtime.remove_from_queue(avid)

                # 发送任务失败通知
                runtime.notify(
                    "task_failed",
                    {
                        "task_id": task_id,
                        "avid": avid,
                        "status": "failed",
                        "message": "下载失败",
                    },
                )
                runtime.notify("queue_status", runtime.queue_status())

                try:
                    self.persistence.mark_failed(avid)
                except Exception as e:
                    logger.warning(f"下载失败后更新 AVResource 失败: {e}")

                return {"status": "failed", "avid": avid, "message": "下载失败"}

        except DownloadLeaseLost:
            raise
        except Exception as e:
            logger.error(f"视频 {avid} 下载异常: {str(e)}")

            # 从 Redis 队列中移除任务
            runtime.remove_from_queue(avid)

            # 发送任务失败通知
            runtime.notify(
                "task_failed",
                {
                    "task_id": task_id,
                    "avid": avid,
                    "status": "failed",
                    "message": f"下载异常: {str(e)}",
                },
            )
            runtime.notify("queue_status", runtime.queue_status())

            # 重试
            try:
                retry(e)
            except DownloadRetriesExhausted:
                try:
                    self.persistence.mark_failed(avid)
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
                runtime.release_slot()
                logger.info(f"已释放全局下载锁: {avid}")
            except Exception as e:
                logger.error(f"释放全局下载锁失败 {avid}: {str(e)}")

            try:
                runtime.remove_lock(avid)
                logger.info(f"已清理任务锁: {avid}")
            except Exception as e:
                logger.error(f"清理任务锁失败 {avid}: {str(e)}")

            # 清理进度信息
            try:
                runtime.remove_progress(avid)
                logger.info(f"已清理任务进度: {avid}")
            except Exception as e:
                logger.error(f"清理任务进度失败 {avid}: {str(e)}")

            # 发送最终队列状态
            runtime.notify("queue_status", runtime.queue_status())


class MockDownloadUseCase(DownloadWorkflow):
    def __init__(self, runtime: DownloadRuntime, sleep: Callable[[float], None]):
        self.runtime, self.sleep = runtime, sleep

    def run(
        self,
        avid: str,
        task_id: str,
        *,
        duration_seconds: int = 30,
        ownership: DownloadOwnership | None = None,
    ) -> dict:
        runtime = self.runtime
        avid = avid.upper()
        logger.info(
            f"[测试] 开始模拟下载任务: {avid}, 任务ID: {task_id}, 持续时间: {duration_seconds}秒"
        )

        # 创建任务锁
        runtime.create_lock(avid, task_id)

        # 更新 Redis 队列中的任务状态为 STARTED
        runtime.set_state(avid, "STARTED")

        # 发送任务开始通知
        runtime.notify(
            "task_started", {"task_id": task_id, "avid": avid, "status": "started"}
        )

        # 发送更新后的队列状态
        runtime.notify("queue_status", runtime.queue_status())

        try:
            # 模拟下载过程，每秒更新进度
            step = 100.0 / duration_seconds
            for i in range(duration_seconds):
                self.sleep(1)
                percent = min(100.0, (i + 1) * step)
                speed = f"{((i + 1) * 2):.1f} MB/s"  # 模拟速度
                remaining = duration_seconds - (i + 1)
                eta = (
                    f"00:00:{remaining:02d}"
                    if remaining < 60
                    else f"00:{remaining // 60:02d}:{remaining % 60:02d}"
                )

                if ownership:
                    ownership.check()
                # 更新进度
                runtime.set_progress(avid, percent, speed, eta=eta)

                # 发送进度通知
                runtime.notify(
                    "progress_update",
                    {
                        "task_id": task_id,
                        "avid": avid,
                        "percent": percent,
                        "speed": speed,
                        "eta": eta,
                    },
                )

            if ownership:
                ownership.check()
            # 模拟下载完成
            logger.info(f"[测试] 模拟下载完成: {avid}")

            # 清理进度和锁
            runtime.remove_progress(avid)
            runtime.remove_lock(avid)

            # 从 Redis 队列中移除任务
            runtime.remove_from_queue(avid)

            # 发送任务完成通知
            runtime.notify(
                "task_completed",
                {
                    "task_id": task_id,
                    "avid": avid,
                    "status": "completed",
                    "message": "模拟下载完成",
                },
            )

            # 发送更新后的队列状态
            runtime.notify("queue_status", runtime.queue_status())

            return {
                "status": "completed",
                "avid": avid,
                "task_id": task_id,
                "message": "模拟下载完成",
            }

        except DownloadLeaseLost:
            raise
        except Exception as e:
            logger.error(f"[测试] 模拟下载失败: {avid}, 错误: {e}")

            # 清理
            runtime.remove_progress(avid)
            runtime.remove_lock(avid)

            # 从 Redis 队列中移除任务
            runtime.remove_from_queue(avid)

            # 发送任务失败通知
            runtime.notify(
                "task_failed",
                {
                    "task_id": task_id,
                    "avid": avid,
                    "status": "failed",
                    "message": f"模拟下载失败: {str(e)}",
                },
            )

            # 发送更新后的队列状态
            runtime.notify("queue_status", runtime.queue_status())

            return {
                "status": "failed",
                "avid": avid,
                "task_id": task_id,
                "error": str(e),
            }
