"""Manifest/marker checked image files; no symlink traversal below configured roots."""

import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import stat
from uuid import UUID

from nassav.resource_file_locks import resource_file_lock
from nassav.resource_reads import ReadLeaseNotFound, ReadLeaseConflict
from nassav.task_models import TaskArtifact, TaskAssetTarget


def asset_identity(asset):
    return hashlib.sha256(f"{asset['root']}:{asset['path']}".encode()).hexdigest()


def image_asset(version, asset_id=None):
    if version.kind != "metadata" or not isinstance(version.manifest, list):
        raise ReadLeaseNotFound("Image not available")
    assets = [
        item
        for item in version.manifest
        if isinstance(item, dict)
        and item.get("root") in {"cover", "avatar"}
        and item.get("kind") == item.get("root")
    ]
    for item in assets:
        if not isinstance(item.get("path"), str):
            raise ReadLeaseNotFound("Image evidence invalid")
        if (asset_id is None and item["kind"] == "cover") or (
            asset_id is not None and asset_identity(item) == asset_id
        ):
            path = PurePosixPath(item["path"])
            if (
                len(path.parts) < 3
                or path.parts[:2] != ("versions", str(version.pk))
                or path.is_absolute()
                or "\\" in item["path"]
                or any(part in {"", ".", ".."} for part in item["path"].split("/"))
                or any(ord(char) < 32 for char in item["path"])
                or type(item.get("size")) is not int
                or not 0 < item["size"] <= 32 * 1024 * 1024
                or not isinstance(item.get("sha256"), str)
                or re.fullmatch("[0-9a-f]{64}", item["sha256"]) is None
            ):
                raise ReadLeaseNotFound("Image evidence invalid")
            try:
                UUID(str(item.get("marker")))
            except (TypeError, ValueError):
                raise ReadLeaseNotFound("Image evidence invalid") from None
            return item
    raise ReadLeaseNotFound("Image not available")


def open_beneath(root, relative):
    directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        parts = PurePosixPath(relative).parts
        for part in parts[:-1]:
            next_directory = os.open(
                part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory
            )
            os.close(directory)
            directory = next_directory
        return os.open(
            parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory
        )
    finally:
        os.close(directory)


class DjangoVersionImageLocator:
    def __init__(self, roots):
        self.roots = {kind: Path(root).resolve() for kind, root in roots.items()}

    def open(self, version, asset_id, authorize):
        asset = image_asset(version, asset_id)
        try:
            with resource_file_lock(
                version.pool.canonical_avid, self.roots["cover"], timeout=5
            ):
                authorize()  # File lock precedes user -> pool -> read lease transaction.
                if TaskArtifact.objects.filter(
                    root=asset["root"], target_path=asset["path"], state="promoting"
                ).exists():
                    raise ReadLeaseConflict("image_publication_pending")
                marker = TaskAssetTarget.objects.filter(
                    root=asset["root"], relative_path=asset["path"]
                ).first()
                if (
                    marker is None
                    or str(marker.marker) != asset["marker"]
                    or marker.sha256 != asset["sha256"]
                ):
                    raise ReadLeaseNotFound("Image ownership changed")
                fd = open_beneath(self.roots[asset["root"]], asset["path"])
                handle = os.fdopen(fd, "rb")
                try:
                    info = os.fstat(handle.fileno())
                    if not stat.S_ISREG(info.st_mode) or info.st_size != asset["size"]:
                        raise ReadLeaseNotFound("Image file changed")
                    digest = hashlib.sha256()
                    for chunk in iter(lambda: handle.read(65536), b""):
                        digest.update(chunk)
                    after = os.fstat(handle.fileno())
                    if digest.hexdigest() != asset["sha256"] or (
                        info.st_size,
                        info.st_mtime_ns,
                        info.st_ctime_ns,
                    ) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                        raise ReadLeaseNotFound("Image content changed")
                    handle.seek(0)
                    return handle, "image/jpeg", asset["size"]
                except BaseException:
                    handle.close()
                    raise
        except TimeoutError:
            raise ReadLeaseConflict("image_busy") from None
        except OSError:
            raise ReadLeaseNotFound("Image file unavailable") from None
