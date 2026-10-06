"""Shared final-resource lock used by publication and deletion."""

import fcntl
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def file_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def resource_file_lock(avid: str, cover_root: Path):
    return file_lock(cover_root.parent / ".nassav-delete-locks" / f"{avid}.lock")
