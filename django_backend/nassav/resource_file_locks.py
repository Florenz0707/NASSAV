"""Shared final-resource lock used by publication and deletion."""

import fcntl
import time
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def file_lock(path: Path, *, timeout=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        if timeout is None:
            fcntl.flock(handle, fcntl.LOCK_EX)
        else:
            deadline = time.monotonic() + timeout
            while True:
                try:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("Resource file lock busy")
                    time.sleep(0.02)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def resource_file_lock(avid: str, cover_root: Path, *, timeout=None):
    return file_lock(
        cover_root.parent / ".nassav-delete-locks" / f"{avid}.lock", timeout=timeout
    )
