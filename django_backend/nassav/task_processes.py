"""Linux execution identity and writer checks; never signal an unverified PID."""

import os
import json
from contextlib import contextmanager
from contextvars import ContextVar
import socket
import time
import signal
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path


_process_scope: ContextVar[dict | None] = ContextVar("task_process_scope", default=None)


@contextmanager
def task_process_scope(token):
    marker = _process_scope.set(
        {"job_id": token.job_id, "attempt_id": token.attempt_id, "owner": token.owner}
    )
    try:
        yield
    finally:
        _process_scope.reset(marker)


def writer_environment() -> dict[str, str]:
    """Inherited by all descendants, even if the parent dies before PID registration."""
    scope = _process_scope.get()
    return {"NASSAV_TASK_WRITER": json.dumps(scope)} if scope else {}


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
        "pid_namespace": os.readlink(f"/proc/{pid}/ns/pid"),
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
            command,
            stdout=output,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env={**os.environ, **writer_environment()},
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


def identity_status(identity: dict) -> str:
    """Dead requires a known local PID namespace; remote/partial identities are unknown."""
    local = process_identity(os.getpid())
    if any(
        identity.get(key) != local[key] for key in ("host", "boot_id", "pid_namespace")
    ):
        return "unknown"
    try:
        actual = process_identity(int(identity["pid"]))
        fields = (
            (Path("/proc") / str(identity["pid"]) / "stat")
            .read_text()
            .rsplit(")", 1)[1]
            .split()
        )
    except (FileNotFoundError, ProcessLookupError):
        return "dead"
    except (KeyError, ValueError, PermissionError):
        return "unknown"
    if actual["start_ticks"] != identity.get("start_ticks") or fields[0] == "Z":
        return "dead"
    return "alive"


def writer_groups(scope: dict, *, not_before: int = 0) -> dict[int, dict]:
    """Find tagged descendants, including children not yet registered in the DB."""
    groups = {}
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            if entry.stat().st_uid != os.getuid():
                continue
            fields = (entry / "stat").read_text().rsplit(")", 1)[1].split()
            if int(fields[19]) < not_before or fields[0] == "Z":
                continue  # A process older than the worker cannot be its descendant.
            environment = (entry / "environ").read_bytes().split(b"\0")
            marker = next(
                (
                    value.split(b"=", 1)[1]
                    for value in environment
                    if value.startswith(b"NASSAV_TASK_WRITER=")
                ),
                None,
            )
            if marker is None or json.loads(marker) != scope:
                continue
            identity = process_identity(int(entry.name))
            if identity_status(identity) == "alive":
                groups[identity["pgid"]] = identity
        except (FileNotFoundError, ProcessLookupError):
            continue
        except (PermissionError, ValueError, json.JSONDecodeError) as error:
            raise TaskWritersAlive("无法核查本地进程归属，保留工作区") from error
    return groups


def stop_owned_writers(scope: dict, recorded: dict) -> None:
    """Stop only dedicated groups whose every live process belongs to this attempt."""
    not_before = int(recorded.get("worker_start_ticks", 0))
    groups = writer_groups(scope, not_before=not_before)
    if recorded.get("pid") and identity_status(recorded) == "unknown":
        raise TaskWritersAlive("下载进程身份无法核查")
    if recorded.get("pgid") and group_writers(int(recorded["pgid"])):
        # The saved PID may be recycled: do not signal it without inherited ownership.
        if int(recorded["pgid"]) not in groups:
            raise TaskWritersAlive("记录的进程组仍有未确认归属的执行器")
    for pgid, identity in groups.items():
        if pgid == os.getpgrp():
            raise TaskWritersAlive("拒绝停止恢复扫描器所在进程组")
        for pid in group_writers(pgid):
            try:
                environment = (
                    (Path("/proc") / str(pid) / "environ").read_bytes().split(b"\0")
                )
                marker = next(
                    (
                        v.split(b"=", 1)[1]
                        for v in environment
                        if v.startswith(b"NASSAV_TASK_WRITER=")
                    ),
                    None,
                )
                if marker is None or json.loads(marker) != scope:
                    raise TaskWritersAlive("进程组包含其他执行，不可自动停止")
            except (FileNotFoundError, ProcessLookupError):
                continue
        if identity_status(identity) != "alive":
            continue
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(pgid, sig)
            except ProcessLookupError:
                break
            deadline = time.monotonic() + 2
            while group_writers(pgid) and time.monotonic() < deadline:
                time.sleep(0.02)
        ensure_group_stopped(pgid)
    if writer_groups(scope, not_before=not_before):
        raise TaskWritersAlive("还有未退出的任务后代进程")
