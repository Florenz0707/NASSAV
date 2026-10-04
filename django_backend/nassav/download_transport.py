"""Transport bindings for legacy task helpers during the staged migration."""

from types import ModuleType
from nassav.download_workflow import DownloadRuntime


class LegacyTaskDownloadRuntime(DownloadRuntime):
    def __init__(self, helpers: ModuleType):
        self.helpers = helpers

    def create_lock(self, avid: str, task_id: str) -> None:
        return self.helpers.create_task_lock(avid, task_id)

    def wait_for_slot(self, max_wait_time: int) -> bool:
        return self.helpers.wait_for_global_download_lock(max_wait_time=max_wait_time)

    def remove_lock(self, avid: str) -> None:
        return self.helpers.remove_task_lock(avid)

    def remove_from_queue(self, avid: str) -> None:
        return self.helpers.remove_task_from_queue(avid)

    def notify(self, event: str, data: dict) -> None:
        return self.helpers.notify_task_update(event, data)

    def queue_status(self) -> dict:
        return self.helpers.get_full_task_queue()

    def set_state(self, avid: str, state: str) -> None:
        return self.helpers.update_task_state_in_queue(avid, state)

    def set_progress(self, avid: str, percent: float, speed: str, *, eta: str) -> None:
        return self.helpers.set_task_progress(avid, percent, speed, eta=eta)

    def release_slot(self) -> None:
        return self.helpers.release_global_download_lock()

    def remove_progress(self, avid: str) -> None:
        return self.helpers.remove_task_progress(avid)
