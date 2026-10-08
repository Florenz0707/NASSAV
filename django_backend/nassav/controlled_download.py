"""Download execution with durable stops, private output and explicit outcomes."""

import json
import time
import os
from collections.abc import Callable
from pathlib import Path
from threading import get_ident

from django.db import close_old_connections
from curl_cffi.requests.exceptions import HTTPError
from nassav.task_network import TaskNetworkControl
from loguru import logger

from nassav.constants import HEADERS
from nassav.download_contracts import DownloadLeaseLost, DownloadOwnership
from nassav.download_resume import (
    DownloadRestartRequired,
    DownloadValidationTimeout,
    HLSResumeGuard,
)
from nassav.task_assets import AssetPromotion, TaskAssets
from nassav.task_control_rules import (
    TaskCancelRequested,
    TaskExecutionInvalid,
    TaskPauseRequested,
)
from nassav.task_processes import (
    TaskWritersAlive,
    process_identity,
    run_media_command,
    task_process_scope,
)
from nassav.task_records import DjangoTaskRecords


def validate_video(
    path: Path, duration: float, check: Callable, started: Callable
) -> bool:
    probe = json.loads(
        run_media_command(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=format_name,duration:stream=codec_type",
                "-of",
                "json",
                str(path),
            ],
            check,
            started,
        )
    )
    actual = float(probe.get("format", {}).get("duration", 0))
    if (
        not any(
            stream.get("codec_type") == "video" for stream in probe.get("streams", [])
        )
        or actual <= 0
        or (duration and actual < duration - max(2, duration * 0.005))
    ):
        raise RuntimeError("视频缺少完整轨道或时长不足")
    # ensure_mp4 renames only; controlled output must be a real MP4 container.
    if "mp4" not in probe["format"].get("format_name", "").split(","):
        converted = path.with_name("verified.mp4")
        run_media_command(
            [
                "ffmpeg",
                "-nostdin",
                "-v",
                "error",
                "-y",
                "-i",
                str(path),
                "-map",
                "0",
                "-c",
                "copy",
                str(converted),
            ],
            check,
            started,
        )
        converted.replace(path)
    run_media_command(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-xerror",
            "-i",
            str(path),
            "-map",
            "0:v:0",
            "-map",
            "0:a?",
            "-f",
            "null",
            "-",
        ],
        check,
        started,
    )
    return True


class ControlledDownload:
    def __init__(
        self,
        records: DjangoTaskRecords,
        assets: TaskAssets,
        resolver,
        downloader,
        lease: DownloadOwnership,
        persist: Callable[[str], None],
        *,
        guard: HLSResumeGuard,
        validate: Callable = validate_video,
        sleep: Callable = time.sleep,
        project: Callable | None = None,
    ):
        self.records, self.assets = records, assets
        self.resolver, self.downloader, self.lease = resolver, downloader, lease
        self.persist, self.guard, self.validate, self.sleep = (
            persist,
            guard,
            validate,
            sleep,
        )
        self.project = project

    def _project(self, snapshot: dict, *, progress: dict | None = None):
        if self.project:
            try:
                self.project(snapshot, progress=progress)
            except DownloadLeaseLost:
                raise
            except Exception:
                logger.exception("任务 {} 的推送/队列投影暂不可用", snapshot["job_id"])

    def run(self, job_id: str, attempt_id: str) -> dict:
        records, lease = self.records, self.lease
        try:
            token = records.claim(job_id, attempt_id, kind="download", role="main")
        except TaskExecutionInvalid:
            return {"status": "ignored", "job_id": job_id}
        job = records.get(job_id)
        avid = job["avid"]
        workspace, manifest = None, None
        error, success = None, False
        writers_confirmed = True
        watchdog_error = []
        execution_thread = get_ident()
        worker_identity = process_identity(os.getpid())
        worker_identity = {
            f"worker_{key}": value for key, value in worker_identity.items()
        }
        last_heartbeat = [0.0]

        def check():
            records.check(token)
            lease.check()
            if time.monotonic() - last_heartbeat[0] >= 1:
                records.heartbeat(token)
                last_heartbeat[0] = time.monotonic()

        def cancelled():
            # CLI watchdog is a separate thread with its own short-lived DB connection.
            try:
                check()
                return False
            except Exception as failure:
                if not watchdog_error:
                    watchdog_error.append(failure)
                return True
            finally:
                if get_ident() != execution_thread:
                    close_old_connections()

        def started(pid):
            records.execution_identity(
                token,
                {
                    **worker_identity,
                    **process_identity(pid),
                    **lease.recovery_identity(),
                },
            )
            check()

        last_progress = [0.0]

        def progress(percent, speed, eta):
            check()
            if time.monotonic() - last_progress[0] >= 1 or percent >= 100:
                last_progress[0] = time.monotonic()
                progress_data = {
                    "percent": percent,
                    "speed": speed,
                    "eta": eta,
                    "updated_at": time.time(),
                }
                snapshot = records.checkpoint(
                    token,
                    records.get(job_id)["stage"] or "video_download",
                    {"progress": progress_data},
                )
                self._project(snapshot, progress=progress_data)

        control = TaskNetworkControl(
            check,
            publish_fence=lambda operation: records.controlled_transaction(
                token, operation
            ),
        )
        try:
            records.execution_identity(
                token, {**worker_identity, **lease.recovery_identity()}
            )
            lease.start()
            check()
            if job["checkpoint"].get("video_committed"):
                success = True
            else:
                records.checkpoint(token, "source_lookup")
                resolved = self.resolver.resolve(avid, control=control)
                check()
                if not resolved or not resolved.info.m3u8:
                    raise RuntimeError("无法获取下载信息")
                headers = {
                    "Referer": f"https://{resolved.domain}/",
                    "User-Agent": HEADERS["User-Agent"],
                }
                records.checkpoint(token, "waiting_slot")
                deadline = time.monotonic() + 1800
                while not lease.acquire_global():
                    check()
                    if time.monotonic() >= deadline:
                        raise RuntimeError("等待下载槽位超时")
                    self.sleep(0.2)
                self._project(records.get(job_id))
                records.checkpoint(token, "resume_validation")
                try:
                    manifest = self.guard.describe(resolved.info.m3u8, headers, check)
                except HTTPError as failure:
                    check()
                    if getattr(failure.response, "status_code", None) not in {
                        401,
                        403,
                        404,
                        410,
                    }:
                        raise
                    # One bounded refresh for rejected/expired links; never bypass resume identity checks.
                    resolved = self.resolver.resolve(avid, control=control, force=True)
                    check()
                    if resolved is None or not resolved.info.m3u8:
                        raise RuntimeError("无法刷新失效播放链接") from failure
                    headers["Referer"] = f"https://{resolved.domain}/"
                    manifest = self.guard.describe(resolved.info.m3u8, headers, check)
                workspace = self.assets.workspace(token, "video")
                self.guard.prepare(
                    workspace,
                    avid,
                    manifest,
                    job["checkpoint"].get("download"),
                    headers,
                    check,
                )
                records.checkpoint(
                    token,
                    "video_download",
                    {"download": {"manifest": manifest, "segments": {}}},
                )
                with task_process_scope(token):
                    completed = self.downloader.download(
                        url=manifest["url"] if manifest["safe"] else resolved.info.m3u8,
                        output_dir=workspace,
                        output_name=avid,
                        referer=headers["Referer"],
                        user_agent=headers["User-Agent"],
                        cancelled=cancelled,
                        progress_callback=progress,
                        process_started=started,
                        stage_callback=lambda stage: records.checkpoint(token, stage),
                    )
                if watchdog_error:
                    raise watchdog_error[0]
                check()
                if not completed:
                    raise RuntimeError("下载器未生成完整视频")
                output = self.downloader.ensure_mp4(workspace, avid)
                if not output:
                    raise RuntimeError("下载输出不存在")
                records.checkpoint(token, "video_verify")
                expected_duration = manifest["duration"]
                with task_process_scope(token):
                    asset_id = self.assets.stage(
                        token,
                        "video",
                        f"download/{avid}.mp4",
                        "video",
                        lambda path: path == output,
                        validate=lambda path: self.validate(
                            path, expected_duration, check, started
                        ),
                        check=check,
                    )
                records.checkpoint(token, "resource_save")

                def persist():
                    lease.check()
                    self.persist(avid)

                self.assets.commit(
                    token,
                    [AssetPromotion(asset_id, f"{avid}.mp4")],
                    persist,
                    checkpoint={"video_committed": True},
                )
                success = True
        except TaskWritersAlive:
            # Do not acknowledge stop or clean when writer exit is unknown.
            writers_confirmed = False
            lease.retain_for_recovery()
            raise
        except Exception as failure:
            error = failure
        finally:
            if writers_confirmed:
                lease.close()

        if isinstance(error, (TaskPauseRequested, TaskCancelRequested)):
            checkpoint = {}
            resume_error = None
            if workspace and manifest:

                def stopped_check():
                    records.owned(token)
                    records.heartbeat(token)

                try:
                    segments = self.guard.snapshot(workspace, avid, stopped_check)
                except DownloadRestartRequired as failure:
                    resume_error = failure
                    segments = {}
                    manifest = {**manifest, "safe": False}
                checkpoint["download"] = {"manifest": manifest, "segments": segments}
            snapshot = records.acknowledge_stop(
                token,
                checkpoint=checkpoint,
                error_code="RESTART_REQUIRED" if resume_error else "",
                message=str(resume_error) if resume_error else "",
            )
        elif isinstance(error, (DownloadRestartRequired, DownloadValidationTimeout)):
            try:
                snapshot = records.suspend(
                    token,
                    error_code="RESUME_VALIDATION_TIMEOUT"
                    if isinstance(error, DownloadValidationTimeout)
                    else "RESTART_REQUIRED",
                    message=str(error),
                )
            except (TaskPauseRequested, TaskCancelRequested):
                snapshot = records.acknowledge_stop(token)
        elif error:
            # A concurrent stop wins over a failure result.
            try:
                snapshot = records.finish(
                    token,
                    "failed",
                    error_code="LEASE_LOST"
                    if isinstance(error, DownloadLeaseLost)
                    else "DOWNLOAD_FAILED",
                    message=str(error)[:200],
                )
            except (TaskPauseRequested, TaskCancelRequested):
                snapshot = records.acknowledge_stop(token)
        elif success:
            try:
                snapshot = records.finish(token, "succeeded")
            except (TaskPauseRequested, TaskCancelRequested):
                snapshot = records.acknowledge_stop(token)
        else:
            raise RuntimeError("下载执行缺少明确结果")
        if snapshot["state"] in {"succeeded", "failed", "cancelled"}:
            snapshot = self.assets.cleanup(job_id)
        self._project(snapshot)
        return {
            "status": snapshot["state"],
            "avid": avid,
            "job_id": job_id,
            "snapshot": snapshot,
        }
