"""Bounded child execution with parent fencing, translation CAS and stop acknowledgement."""

import logging
import os
import time

from nassav.task_control_rules import (
    TaskCancelRequested,
    TaskExecutionInvalid,
    TaskPauseRequested,
)
from nassav.task_network import TaskNetworkControl
from nassav.task_processes import process_identity
from nassav.translation_contracts import TranslationSuperseded

logger = logging.getLogger(__name__)


class ControlledTranslation:
    def __init__(self, records, assets, repository, translator, project=None):
        self.records, self.assets, self.repository = records, assets, repository
        self.translator, self.project = translator, project

    def run(self, job_id: str, attempt_id: str) -> dict:
        records = self.records
        try:
            token = records.claim(job_id, attempt_id, kind="scrape", role="translation")
        except TaskExecutionInvalid:
            return {"status": "ignored", "job_id": job_id}
        claim = None
        heartbeat = [0.0]

        def check():
            records.check(token)
            if time.monotonic() - heartbeat[0] >= 1:
                records.heartbeat(token)
                heartbeat[0] = time.monotonic()

        def notify(snapshot):
            if self.project:
                try:
                    self.project(snapshot)
                except Exception:
                    logger.exception("翻译快照推送失败: %s", job_id)

        def stopped():
            if claim:
                records.controlled_transaction(
                    token,
                    lambda: self.repository.interrupt(
                        claim,
                        cancel=records.get(job_id)["requested_action"] == "cancel",
                    ),
                    allow_stopping=True,
                )
            return records.acknowledge_stop(token)

        try:
            records.execution_identity(
                token,
                {
                    f"worker_{key}": value
                    for key, value in process_identity(os.getpid()).items()
                },
            )
            checkpoint = records.get(job_id)["checkpoint"]
            base = checkpoint.get("translation_claim") or checkpoint["translation_base"]
            claim, snapshot = records.translation_transaction(
                token,
                "translating",
                lambda: self.repository.begin(base, token.attempt_id),
                checkpoint=lambda value: {"translation_claim": value},
            )
            notify(snapshot)
            control = TaskNetworkControl(check)
            translated = None
            if claim["title"]:
                with control.phase(180):
                    translated = self.translator(control).translate(claim["title"])
                    control.check()
            check()
            state = (
                "skipped"
                if not claim["title"]
                else "completed"
                if translated
                else "failed"
            )
            _, snapshot = records.translation_transaction(
                token, state, lambda: self.repository.apply(claim, translated)
            )
            notify(snapshot)
            snapshot = records.finish(
                token,
                "failed" if state == "failed" else "succeeded",
                error_code="TRANSLATION_FAILED" if state == "failed" else "",
            )
        except (TaskPauseRequested, TaskCancelRequested):
            snapshot = stopped()
        except TranslationSuperseded:
            try:
                _, snapshot = records.translation_transaction(
                    token, "superseded", lambda: None
                )
                snapshot = records.finish(
                    token,
                    "failed",
                    error_code="TRANSLATION_SUPERSEDED",
                    message="资源已保存，翻译已被更新操作替代",
                )
            except (TaskPauseRequested, TaskCancelRequested):
                snapshot = stopped()
        except TaskExecutionInvalid:
            return {"status": "ignored", "job_id": job_id}
        except Exception:
            logger.exception("父任务翻译执行失败: %s", job_id)
            try:
                check()
                if claim:
                    records.translation_transaction(
                        token, "failed", lambda: self.repository.apply(claim, None)
                    )
                else:
                    records.translation_transaction(token, "failed", lambda: None)
                snapshot = records.finish(
                    token,
                    "failed",
                    error_code="TRANSLATION_FAILED",
                    message="资源已保存，翻译失败",
                )
            except (TaskPauseRequested, TaskCancelRequested):
                snapshot = stopped()
            except TranslationSuperseded:
                records.translation_transaction(token, "superseded", lambda: None)
                snapshot = records.finish(
                    token, "failed", error_code="TRANSLATION_SUPERSEDED"
                )
        if snapshot["cleanup_state"] == "pending":
            snapshot = self.assets.cleanup(job_id)
        notify(snapshot)
        return snapshot
