"""Worker-owned recovery loop, independent of optional beat and browser sessions."""

import logging
from threading import Event, Thread

from celery.signals import worker_ready, worker_shutdown

logger = logging.getLogger(__name__)
_stop = Event()
_thread = None


def recovery_loop():
    from django.conf import settings
    from django.db import close_old_connections
    from nassav.composition import build_task_recovery

    interval = max(5, getattr(settings, "TASK_RECOVERY_INTERVAL", 15))
    while not _stop.is_set():
        try:
            close_old_connections()
            build_task_recovery().scan()
        except Exception:
            logger.exception("Persistent task recovery scan failed")
        try:
            from nassav.recommendation.jobs import recover

            recover()
        except Exception:
            logger.exception("Recommendation recovery scan failed")
        try:
            if getattr(settings, "PLAYBACK_ENABLED", False):
                from nassav.playback.records import recover
                from nassav.tasks import playback_prepare_task

                recover(
                    lambda session_id: playback_prepare_task.apply_async(
                        args=(session_id,), queue="scrape"
                    )
                )
        except Exception:
            logger.exception("Playback recovery scan failed")
        finally:
            close_old_connections()
        _stop.wait(interval)


@worker_ready.connect
def start_recovery(**kwargs):
    from django.conf import settings

    global _thread
    if not getattr(settings, "TASK_RECOVERY_ENABLED", True):
        return
    if _thread is not None and _thread.is_alive():
        return
    _stop.clear()
    _thread = Thread(target=recovery_loop, name="nassav-task-recovery", daemon=True)
    _thread.start()


@worker_shutdown.connect
def stop_recovery(**kwargs):
    _stop.set()
    if _thread is not None:
        _thread.join(timeout=3)
