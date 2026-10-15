"""Bounded cached image handles beneath a configured, resolved root."""

import os
from pathlib import Path
import stat
from nassav.resource_reads import ReadLeaseNotFound
from nassav.version_image_files import open_beneath


def open_cache_image(root, path):
    fd = None
    try:
        root = Path(root).resolve()
        fd = open_beneath(root, Path(path).relative_to(root).as_posix())
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= 5 * 1024 * 1024:
            raise ReadLeaseNotFound("Image unavailable")
        handle = os.fdopen(fd, "rb")
        fd = None
        return handle
    except (OSError, ValueError):
        raise ReadLeaseNotFound("Image unavailable") from None
    finally:
        if fd is not None:
            os.close(fd)


def cache_directory(root, relative):
    """Create and pin a cache directory without following child symlinks."""
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in Path(relative).parts:
            if part in {"..", ".", "/"}:
                raise ValueError("Invalid cache directory")
            try:
                os.mkdir(part, mode=0o700, dir_fd=directory)
            except FileExistsError:
                pass
            child = os.open(
                part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory
            )
            os.close(directory)
            directory = child
        result, directory = directory, None
        return result
    finally:
        if directory is not None:
            os.close(directory)
