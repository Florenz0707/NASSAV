"""ID-only maintenance tasks; default-closed and independent of browser lifetime."""

from celery import shared_task
from django.conf import settings
from nassav.resource_gc import GcDeferred


@shared_task(name="nassav.tasks.resource_gc_task", ignore_result=True)
def resource_gc_task(job_id):
    if not settings.SHARED_LIBRARY_ENABLED or not settings.RESOURCE_GC_ENABLED:
        return {"state": "disabled"}
    from nassav.composition import build_resource_reclaimer

    try:
        return build_resource_reclaimer().run(job_id)
    except (GcDeferred, TimeoutError):
        return {"state": "deferred"}


def recover_resource_gc():
    if not settings.SHARED_LIBRARY_ENABLED or not settings.RESOURCE_GC_ENABLED:
        return {"discovered": 0, "dispatched": 0}
    from nassav.resource_gc_dispatch import GcDispatcher
    from nassav.resource_gc_records import DjangoGcRecords

    dispatcher = GcDispatcher(
        DjangoGcRecords(),
        lambda job_id: resource_gc_task.apply_async(
            args=(job_id,), queue="default", expires=300
        ),
    )
    discovered = dispatcher.discover(settings.RESOURCE_GC_BATCH_SIZE)
    return {
        "discovered": len(discovered),
        "dispatched": dispatcher.recover(settings.RESOURCE_GC_BATCH_SIZE),
    }
