"""Fenced Redis compatibility projection and versioned Channels hints."""

import json

from nassav import download_queue
from nassav.download_contracts import DownloadLeaseLost, DownloadOwnership


class DownloadTaskProjection:
    def __init__(self, lease: DownloadOwnership):
        self.lease = lease

    def __call__(self, snapshot: dict, *, progress: dict | None = None):
        if snapshot["state"] == "running":
            if not self.lease.mutate("state", "STARTED"):
                raise DownloadLeaseLost("任务队列投影时租约已丢失")
            if progress is not None and not self.lease.mutate(
                "progress", json.dumps(progress)
            ):
                raise DownloadLeaseLost("任务进度投影时租约已丢失")
        download_queue.notify_task_update(
            "task_job_update",
            {
                "job_id": snapshot["job_id"],
                "job_type": snapshot["job_type"],
                "version": snapshot["version"],
            },
        )
        if progress is None:
            download_queue.notify_task_update(
                "queue_status", download_queue.get_full_task_queue()
            )
