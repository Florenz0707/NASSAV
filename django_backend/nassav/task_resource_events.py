"""Durable resource-commit events; consumers deduplicate the stable event UUID."""

from django.utils import timezone

from nassav.resource_file_locks import file_lock
from nassav.task_models import TaskEvent, TaskEventReceipt, TaskJob


def record_resource_event(job_id: str, event: str) -> None:
    # Called inside the fenced resource transaction, never after it.
    TaskEvent.objects.get_or_create(job_id=job_id, event=event)


def receive_once(event_id: str | None, consumer: str) -> bool:
    if not event_id:
        return True
    return TaskEventReceipt.objects.get_or_create(event_id=event_id, consumer=consumer)[
        1
    ]


class TaskResourceEvents:
    def __init__(self, lock_dir, publish):
        self.lock_dir, self.publish = lock_dir, publish

    def flush(self, job_id: str) -> None:
        with file_lock(self.lock_dir / f"{job_id}.lock"):
            job = TaskJob.objects.get(pk=job_id)
            if not job.resource_saved:
                return
            for event in TaskEvent.objects.filter(job=job, state="pending").order_by(
                "created_at"
            ):
                self.publish(event.event, job.avid, str(event.id))
                event.state = "sent"
                event.delivered_at = timezone.now()
                event.save(update_fields=["state", "delivered_at"])
