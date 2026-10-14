"""Shared attempts use ID-only messages and never enter legacy queue projections."""

from django.conf import settings

from nassav.task_records import DjangoTaskRecords


def dispatch_shared(records=None, *, sender=None):
    if not settings.SHARED_LIBRARY_ENABLED:
        return {"sent": 0, "failed": 0}
    records = (
        records if records is not None else DjangoTaskRecords(shared_execution=True)
    )
    if sender is None:
        from nassav.shared_work_tasks import shared_work_task

        def send(ticket):
            shared_work_task.apply_async(
                args=(ticket["job_id"],),
                task_id=ticket["task_id"],
                queue="download" if ticket["kind"] == "download" else "scrape",
            )

        sender = send

    return records.dispatch_pending(sender, shared_only=True)
