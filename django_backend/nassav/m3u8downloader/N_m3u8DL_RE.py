"""
N_m3u8DL-RE 下载器实现
https://github.com/nilaoda/N_m3u8DL-RE
"""

import os
import platform
import re
import signal
import subprocess
from collections.abc import Callable
from pathlib import Path
from threading import Event, Thread

from django.conf import settings
from loguru import logger

from nassav.task_processes import writer_environment

from .M3u8DownloaderBase import M3u8DownloaderBase


class _DownloadDiagnostics:
    """Keep fixed failure categories and bounded numbers, never native output."""

    def __init__(self):
        self.statuses = set()
        self.segment_counts = None
        self.failed = False
        self.signals = set()

    def observe(self, line: str):
        line = re.sub(r"\x1b\[[0-9;]*m", "", line[:4096])
        status = re.search(
            r"Response status code does not indicate success:\s*([1-5]\d{2})\b",
            line,
        )
        if status and len(self.statuses) < 8:
            self.statuses.add(int(status.group(1)))
        counts = re.search(
            r"Segment count check not pass,\s*total:\s*(\d{1,9}),\s*downloaded:\s*(\d{1,9})\b",
            line,
        )
        if counts:
            self.segment_counts = tuple(map(int, counts.groups()))
            self.failed = True
        if re.search(r"\bERROR\s*:\s*Failed\b", line):
            self.failed = True
        for phrase, category in (
            ("too many open files", "too_many_open_files"),
            ("argument list too long", "argument_list_too_long"),
            ("no space left on device", "disk_full"),
            ("permission denied", "permission_denied"),
        ):
            if phrase in line.lower():
                self.signals.add(category)

    def summary(self, returncode: int) -> str:
        facts = [f"退出码 {returncode}"]
        facts.extend(f"上游 HTTP {status}" for status in sorted(self.statuses))
        if self.segment_counts is not None:
            total, downloaded = self.segment_counts
            facts.append(f"分片 {downloaded}/{total}")
        facts.extend(sorted(self.signals))
        return "下载器未生成完整视频（" + "；".join(facts) + "）"


class N_m3u8DL_RE(M3u8DownloaderBase):
    """N_m3u8DL-RE 下载器"""

    SPEED_PATTERN = r"([\d.]+\s*[KMGT]?i?B(?:/s|ps))"

    def __init__(self, proxy: str | None = None):
        super().__init__(proxy)

        # 工具路径
        tools_dir = settings.BASE_DIR / "tools"
        if platform.system() == "Windows":
            self.tool_path = str(tools_dir / "N_m3u8DL-RE.exe")
        else:
            self.tool_path = str(tools_dir / "N_m3u8DL-RE")

    def get_downloader_name(self) -> str:
        return "N_m3u8DL-RE"

    def download(
        self,
        url: str,
        output_dir: Path,
        output_name: str,
        referer: str,
        user_agent: str,
        thread_count: int = 4,
        retry_count: int = 5,
        progress_callback: Callable | None = None,
        cancelled: Callable[[], bool] | None = None,
        process_started: Callable[[int], None] | None = None,
        stage_callback: Callable[[str], None] | None = None,
    ) -> bool:
        """使用 N_m3u8DL-RE 下载 M3U8 视频

        Args:
            progress_callback: 进度回调函数，参数为 (percent: float, speed: str, eta: str)
        """
        if cancelled and cancelled():
            return False
        output_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = output_dir / "temp"

        process = None
        watchdog = None
        stopped = Event()
        cancelled_run = Event()
        diagnostics = _DownloadDiagnostics()

        def failed(returncode):
            message = diagnostics.summary(returncode)
            logger.error("[{}] {}", output_name, message)
            if process_started is not None:
                raise RuntimeError(message)
            return False

        try:
            # 构建命令
            cmd = [
                self.tool_path,
                url,
                "--tmp-dir",
                str(tmp_path),
                "--save-dir",
                str(output_dir),
                "--save-name",
                output_name,
                "--thread-count",
                str(thread_count),
                "--download-retry-count",
                str(retry_count),
                "--del-after-done",  # 下载完成后删除临时文件
                "false" if process_started is not None else "true",
                "--auto-select",  # 自动选择最佳质量
                "--no-log",  # 禁用日志文件
                "--disable-update-check",
                "-H",
                f"Referer: {referer}",
                "-H",
                f"User-Agent: {user_agent}",
            ]

            # Only the dedicated download proxy may affect the downloader.
            env = os.environ.copy()
            env.update(COLUMNS="120", LINES="40", TERM="xterm")
            for key in (
                "http_proxy",
                "https_proxy",
                "HTTP_PROXY",
                "HTTPS_PROXY",
                "ALL_PROXY",
                "all_proxy",
                "NO_PROXY",
                "no_proxy",
            ):
                env.pop(key, None)
            if self.proxy:
                env["http_proxy"] = self.proxy
                env["https_proxy"] = self.proxy
                env["HTTP_PROXY"] = self.proxy
                env["HTTPS_PROXY"] = self.proxy

            env.update(writer_environment())
            # 使用 Popen 实时读取输出
            process = subprocess.Popen(
                cmd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1,
                start_new_session=(os.name == "posix"),
            )
            if process_started:
                process_started(process.pid)

            if cancelled is not None:

                def watch_cancellation():
                    while not stopped.wait(0.1):
                        try:
                            should_stop = cancelled()
                        except Exception:
                            should_stop = True
                        if should_stop:
                            cancelled_run.set()
                            self._terminate_process(process)
                            return

                watchdog = Thread(target=watch_cancellation, daemon=True)
                watchdog.start()

            # 实时读取输出并解析进度
            if process.stdout:
                for line in process.stdout:
                    # 解析进度信息（示例格式: "已下载: 45.2% | 速度: 5.2MB/s"）
                    line = line.strip()
                    diagnostics.observe(line)
                    if stage_callback and any(
                        word in line.lower()
                        for word in ("merging", "muxing", "合并", "混流")
                    ):
                        stage_callback("merging")
                    if progress_callback:
                        # 尝试匹配百分比
                        percent_match = re.search(r"(\d+\.?\d*)%", line)
                        # 尝试匹配速度
                        speed_match = re.search(
                            self.SPEED_PATTERN,
                            line,
                            re.IGNORECASE,
                        )

                        if percent_match:
                            percent = float(percent_match.group(1))
                            speed = speed_match.group(1) if speed_match else "N/A"
                            try:
                                progress_callback(percent, speed, "")
                            except Exception as e:
                                logger.error(f"进度回调失败: {e}")

            # 等待进程完成
            returncode = process.wait()

            if cancelled_run.is_set() or (cancelled and cancelled()):
                return False
            if returncode != 0 or diagnostics.failed:
                return failed(returncode)

            # 检查输出文件
            output_file = self.get_output_file(output_dir, output_name)
            if output_file:
                file_size = output_file.stat().st_size
                size_mb = file_size / (1024 * 1024)
                logger.info(f"[{output_name}] 下载完成: {size_mb:.1f} MB")
                return True
            else:
                return failed(returncode)

        except FileNotFoundError:
            logger.error(f"N_m3u8DL-RE 工具不存在: {self.tool_path}")
            return False
        except Exception as e:
            logger.error(f"下载失败: {e}")
            if process_started is not None:
                raise
            return False

        finally:
            stopped.set()
            if watchdog is not None:
                watchdog.join(timeout=3)
            if process is not None and cancelled_run.is_set():
                self._terminate_process(process)
            if process is not None and process_started is not None:
                # Controlled calls confirm all descendants, including quiet CLI paths.
                self._terminate_process(process)
                from nassav.task_processes import ensure_group_stopped

                ensure_group_stopped(process.pid)
            if process is not None and process.stdout is not None:
                close = getattr(process.stdout, "close", None)
                if close:
                    close()

    @staticmethod
    def _terminate_process(process) -> None:
        if process is None:
            return
        try:
            if os.name == "posix":
                # The parent may have exited while a descendant still owns the
                # output pipe. Reap the complete execution group in either case.
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    pass
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=2)
            elif process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
        except ProcessLookupError:
            pass
