"""Checkpointed scrape workflow; network preparation and ORM commits are explicit seams."""

import hashlib
import logging
import os
import time

from nassav.scrape_preparation import resource_input, valid_image
from nassav.task_assets import AssetPromotion, TaskAssetError
from nassav.task_control_rules import (
    TaskCancelRequested,
    TaskExecutionInvalid,
    TaskPauseRequested,
)
from nassav.task_network import TaskNetworkControl, TaskNetworkTimeout
from nassav.task_processes import process_identity

from nassav.translation_contracts import translation_identity

logger = logging.getLogger(__name__)


class ControlledScrape:
    def __init__(
        self,
        records,
        assets,
        preparation,
        revision,
        persist,
        events,
        *,
        continuation=None,
        project=None,
        existing=None,
        publication=None,
    ):
        self.records, self.assets, self.preparation = records, assets, preparation
        self.revision, self.persist, self.events = revision, persist, events
        self.continuation, self.project = continuation, project
        self.existing = existing
        self.publication = publication

    def _project(self, snapshot):
        if self.project is not None:
            try:
                self.project(snapshot)
            except Exception:
                logger.exception("任务快照推送失败: %s", snapshot["job_id"])

    def run(self, job_id: str, attempt_id: str) -> dict:
        records, assets = self.records, self.assets
        try:
            token = records.claim(job_id, attempt_id, kind="scrape", role="main")
        except TaskExecutionInvalid:
            return {"status": "ignored", "job_id": job_id}
        snapshot = records.get(job_id)
        options = records.configuration(job_id)
        checkpoint = dict(snapshot["checkpoint"])
        heartbeat = [0.0]

        def check():
            records.check(token)
            if time.monotonic() - heartbeat[0] >= 1:
                records.heartbeat(token)
                heartbeat[0] = time.monotonic()

        def stage(name, **data):
            nonlocal checkpoint
            checkpoint.update(data)
            self._project(records.checkpoint(token, name, data))

        control = TaskNetworkControl(
            check,
            publish_fence=lambda operation: records.controlled_transaction(
                token, operation
            ),
        )
        try:
            gateway = self.preparation(control)
            records.execution_identity(
                token,
                {
                    f"worker_{key}": value
                    for key, value in process_identity(os.getpid()).items()
                },
            )
            if self.publication is not None:
                self.publication.begin(token)
            if (
                not snapshot["resource_saved"]
                and snapshot["action"] == "refresh"
                and not options.get("refresh_metadata", True)
                and not options.get("refresh_m3u8", True)
            ):
                stage("saving")
                if self.existing is None:
                    raise ValueError("未配置已有资源准备能力")
                existing = self.existing
                assets.commit(
                    token,
                    [],
                    lambda: existing(snapshot["avid"]),
                    resource_saved=True,
                    checkpoint=lambda resource: {
                        "resource_committed": True,
                        "translation_base": translation_identity(resource),
                    },
                )
                snapshot = records.get(job_id)
            if not snapshot["resource_saved"]:
                if "base_revision" not in checkpoint:
                    # Version publication owns membership/parent/pointer fencing.
                    # Legacy AVResource existence is not authority for that path,
                    # including the first refresh of an imported membership.
                    base = None
                    if self.publication is None:
                        base = self.revision(snapshot["avid"])
                        if snapshot["action"] == "add" and base is not None:
                            raise ValueError("资源已存在")
                        if snapshot["action"] == "refresh" and base is None:
                            raise ValueError("资源不存在")
                    stage("source", base_revision=base)
                if "prepared" not in checkpoint:
                    stage("source")
                    prepared, page = gateway.source(
                        snapshot["avid"],
                        options.get("source", "any"),
                        force=snapshot["action"] == "refresh",
                    )
                    if page is not None:
                        assets.stage(
                            token,
                            "cover",
                            "page.html",
                            "html",
                            lambda path: control.write(path, page) or True,
                        )
                    stage("source_complete", prepared=prepared)
                prepared = dict(checkpoint["prepared"])
                if not checkpoint.get("metadata_done"):
                    stage("metadata")
                    if options.get("refresh_metadata", True):
                        try:
                            prepared.update(
                                gateway.scrape(
                                    snapshot["avid"],
                                    force=snapshot["action"] == "refresh",
                                )
                            )
                        except TaskNetworkTimeout:
                            prepared.update(metadata=None, scraped_by=None)
                    stage("metadata_complete", prepared=prepared, metadata_done=True)
                page_artifact = assets.completed(token, "cover", "page.html")
                promotions = []
                if page_artifact is not None:
                    target = self._target(
                        token, "cover", f"{snapshot['avid']}.html", "html"
                    )
                    if target is not None:
                        promotions.append(AssetPromotion(page_artifact, target))
                if not checkpoint.get("cover_done"):
                    stage("cover")
                    cover = assets.completed(token, "cover", "cover.jpg")
                    if cover is None and options.get("refresh_metadata", True):
                        try:
                            cover = assets.stage(
                                token,
                                "cover",
                                "cover.jpg",
                                "cover",
                                lambda path: gateway.cover(prepared, path),
                                validate=valid_image,
                            )
                        except (TaskAssetError, TaskNetworkTimeout):
                            check()
                    stage("cover_complete", cover_done=True, cover_artifact=cover)
                if checkpoint.get("cover_artifact"):
                    promotions.append(
                        AssetPromotion(
                            checkpoint["cover_artifact"],
                            self._target(
                                token, "cover", f"{snapshot['avid']}.jpg", "cover"
                            ),
                        )
                    )
                done = dict(checkpoint.get("avatars_done", {}))
                for name, url in gateway.avatars(prepared):
                    check()
                    if (
                        not name
                        or name in {".", ".."}
                        or any(char in name for char in "/\\")
                        or any(ord(char) < 32 for char in name)
                    ):
                        continue
                    if name not in done:
                        stage("avatars")
                        target = self._target(token, "avatar", f"{name}.jpg", "avatar")
                        artifact = None
                        if not assets.valid_existing("avatar", target, valid_image):
                            relative = f"avatars/{hashlib.sha256(name.encode()).hexdigest()}.jpg"
                            artifact = assets.completed(token, "avatar", relative)
                            if artifact is None:
                                try:
                                    artifact = assets.stage(
                                        token,
                                        "avatar",
                                        relative,
                                        "avatar",
                                        lambda path: gateway.avatar(url, path),
                                        validate=valid_image,
                                    )
                                except (TaskAssetError, TaskNetworkTimeout):
                                    check()
                        done[name] = artifact
                        stage("avatars", avatars_done=done)
                    if done[name]:
                        promotions.append(
                            AssetPromotion(
                                done[name],
                                self._target(token, "avatar", f"{name}.jpg", "avatar"),
                                reuse_existing=True,
                                reuse_if=valid_image,
                            )
                        )
                stage("saving")
                data = resource_input(snapshot["avid"], prepared)
                if self.publication is not None:
                    data = self.publication.prepare(token, data, control)
                assets.commit(
                    token,
                    promotions,
                    lambda: self.persist(
                        token, data, checkpoint["base_revision"], snapshot["action"]
                    ),
                    resource_saved=True,
                    checkpoint=self.publication.checkpoint
                    if self.publication is not None
                    else lambda resource: {
                        "resource_committed": True,
                        "translation_base": translation_identity(resource),
                    },
                )
                stage("saved")
            # Committed events survive stop/dispatch failure; they are independent of an attempt.
            try:
                self.events.flush(job_id)
            except Exception:
                logger.exception("已提交资源事件待重试: %s", job_id)
            check()
            if self.continuation is not None:
                snapshot = self.continuation(token)
            else:
                snapshot = records.finish(token, "succeeded")
        except (TaskPauseRequested, TaskCancelRequested):
            # All network/file operations are synchronous and have unwound before acknowledgement.
            snapshot = records.acknowledge_stop(token, checkpoint=checkpoint)
        except TaskExecutionInvalid:
            return {"status": "ignored", "job_id": job_id}
        except Exception:
            logger.exception("受控刮削失败: %s", job_id)
            try:
                # finish itself checks execution/control ownership. Re-checking
                # an invalid source here would strand a still-owned attempt.
                snapshot = records.finish(
                    token,
                    "failed",
                    error_code="SCRAPE_FAILED",
                    message="刮削失败，请查看后端日志",
                )
            except (TaskPauseRequested, TaskCancelRequested):
                snapshot = records.acknowledge_stop(token, checkpoint=checkpoint)
            except TaskExecutionInvalid:
                return {"status": "ignored", "job_id": job_id}
        if snapshot["cleanup_state"] == "pending":
            snapshot = assets.cleanup(job_id)
        self._project(snapshot)
        return snapshot

    def _target(self, token, root, name, kind):
        return (
            self.publication.target(token, root, name, kind)
            if self.publication is not None
            else name
        )
