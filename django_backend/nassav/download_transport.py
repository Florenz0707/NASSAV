"""Redis and Channels adapter for the download workflow runtime."""

from nassav import download_queue
from nassav.download_contracts import DownloadRuntime


class RedisDownloadRuntime(DownloadRuntime):
    def create_lock(self, avid: str, task_id: str) -> None:
        return download_queue.create_task_lock(avid, task_id)

    def wait_for_slot(self, max_wait_time: int) -> bool:
        return download_queue.wait_for_global_download_lock(max_wait_time=max_wait_time)

    def remove_lock(self, avid: str) -> None:
        return download_queue.remove_task_lock(avid)

    def remove_from_queue(self, avid: str) -> None:
        return download_queue.remove_task_from_queue(avid)

    def notify(self, event: str, data: dict) -> None:
        return download_queue.notify_task_update(event, data)

    def queue_status(self) -> dict:
        return download_queue.get_full_task_queue()

    def set_state(self, avid: str, state: str) -> None:
        return download_queue.update_task_state_in_queue(avid, state)

    def set_progress(self, avid: str, percent: float, speed: str, *, eta: str) -> None:
        return download_queue.set_task_progress(avid, percent, speed, eta=eta)

    def release_slot(self) -> None:
        download_queue.release_global_download_lock()

    def remove_progress(self, avid: str) -> None:
        return download_queue.remove_task_progress(avid)
