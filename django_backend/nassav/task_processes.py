"""Linux execution identity and writer checks; never signal an unverified PID."""

import os
import socket
import time
import signal
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path


class TaskWritersAlive(RuntimeError):
    pass


def process_identity(pid: int) -> dict:
    fields = (Path("/proc") / str(pid) / "stat").read_text().rsplit(")", 1)[1].split()
    return {
        "host": socket.gethostname(),
        "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
        "pid": pid,
        "pgid": int(fields[2]),
        "start_ticks": fields[19],
    }


def group_writers(pgid: int) -> list[int]:
    writers = []
    if os.name != "posix" or not Path("/proc").exists():
        raise TaskWritersAlive("当前平台不能验证任务后代进程退出")
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            fields = (entry / "stat").read_text().rsplit(")", 1)[1].split()
            if int(fields[2]) == pgid and fields[0] != "Z":
                writers.append(int(entry.name))
        except (FileNotFoundError, ProcessLookupError):
            continue
    return writers


def ensure_group_stopped(pgid: int) -> None:
    deadline = time.monotonic() + 2
    while group_writers(pgid):
        if time.monotonic() >= deadline:
            raise TaskWritersAlive("任务后代进程尚未退出，保留工作区")
        time.sleep(0.02)


def stop_process(process) -> None:
    try:
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
    except ProcessLookupError:
        process.wait(timeout=2)
    ensure_group_stopped(process.pid)


def run_media_command(
    command: list[str], check: Callable, started: Callable[[int], None]
) -> str:
    """Cancelable validation/remux; bounded output and a dedicated process group."""
    check()
    with tempfile.TemporaryFile() as output:
        process = subprocess.Popen(
            command, stdout=output, stderr=subprocess.STDOUT, start_new_session=True
        )
        try:
            started(process.pid)
            while process.poll() is None:
                check()
                try:
                    process.wait(timeout=0.2)
                except subprocess.TimeoutExpired:
                    continue
            check()
            if process.returncode:
                raise RuntimeError("视频格式或完整性验证失败")
            output.seek(0)
            return output.read(64 * 1024).decode(errors="replace")
        finally:
            stop_process(process)
