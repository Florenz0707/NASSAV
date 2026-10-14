"""Dispose per-workflow transports after all synchronous writers unwind."""

import logging

logger = logging.getLogger(__name__)


class WorkflowResources:
    def __init__(self, workflow, cleanups):
        self.workflow, self.cleanups = workflow, cleanups

    def run(self, job_id, attempt_id):
        try:
            return self.workflow.run(job_id, attempt_id)
        finally:
            self.close()

    def close(self):
        for close in reversed(self.cleanups):
            try:
                close()
            except Exception:
                logger.exception("Shared workflow transport cleanup failed")
