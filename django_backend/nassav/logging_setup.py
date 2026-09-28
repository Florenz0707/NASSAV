"""Install one application file sink per process, including forked workers."""

import os
from pathlib import Path

from loguru import logger

_configured_pid: int | None = None
_sink_id: int | None = None
_log_dir: Path | None = None
_fork_registered = False


def _after_fork() -> None:
    if _log_dir is not None:
        configure_file_logging(_log_dir)


def configure_file_logging(log_dir: Path) -> None:
    global _configured_pid, _sink_id, _log_dir, _fork_registered
    pid = os.getpid()
    if _configured_pid == pid:
        return
    if _sink_id is not None:
        logger.remove(_sink_id)
    _sink_id = logger.add(
        str(log_dir / "{time:YYYY-MM-DD}.log"),
        rotation="00:00",
        retention="30 days",
        enqueue=False,
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
    )
    _configured_pid = pid
    _log_dir = log_dir
    if hasattr(os, "register_at_fork") and not _fork_registered:
        os.register_at_fork(after_in_child=_after_fork)
        _fork_registered = True
