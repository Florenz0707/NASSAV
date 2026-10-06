"""Celery submission Adapter; durable pending attempts survive publication failure."""

from dataclasses import dataclass

from loguru import logger


@dataclass(frozen=True)
class SubmittedTask:
    id: str
    job_id: str


def dispatch_downloads(records=None) -> dict:
    from nassav.composition import build_task_records
    from nassav.tasks import download_video_task
    from nassav import download_queue

    records = records if records is not None else build_task_records()

    def send(ticket):
        # Compatibility projection precedes publication; an eager/fast worker may finish.
        try:
            download_queue.add_task_to_queue(
                ticket["avid"], ticket["task_id"], task_type="download"
            )
        except Exception:
            logger.exception("任务 {} 的 Redis 队列投影暂不可用", ticket["job_id"])
        download_video_task.apply_async(
            args=(ticket["avid"],),
            kwargs={"job_id": ticket["job_id"]},
            task_id=ticket["task_id"],
        )

    return records.dispatch_pending(send, kind="download")


def submit_download(avid: str, owner_id: int | None) -> tuple[SubmittedTask, bool]:
    from nassav.composition import build_task_records

    records = build_task_records()
    snapshot, duplicate = records.create(
        "download", avid, owner_id=owner_id, action="download"
    )
    if not duplicate:
        dispatch_downloads(records)
    return SubmittedTask(snapshot["task_id"], snapshot["job_id"]), duplicate
