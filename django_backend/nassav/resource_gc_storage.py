"""Version-owned unlink only: shared flock, no symlink traversal, hash outside DB."""

from contextlib import ExitStack, contextmanager
import hashlib
import os
from pathlib import Path, PurePosixPath
import stat
import time
from uuid import UUID

from nassav.resource_file_locks import file_lock, resource_file_lock
from nassav.resource_gc import GcDeferred, GcEvidenceError
from nassav.resource_gc_records import manifest_assets
from nassav.resource_version_models import ResourceVersion
from nassav.task_models import TaskJob
from nassav.resource_gc_models import ResourceGcAsset
from nassav.task_control_rules import normalize_avid, TERMINAL_STATES


def fingerprint(value):
    return {
        "device": value.st_dev,
        "inode": value.st_ino,
        "size": value.st_size,
        "mtime_ns": value.st_mtime_ns,
        "ctime_ns": value.st_ctime_ns,
    }


@contextmanager
def parent_directory(root, relative):
    parts = PurePosixPath(relative).parts
    if (
        not parts
        or PurePosixPath(relative).is_absolute()
        or any(part in {"", "..", "."} for part in str(relative).split("/"))
        or "\\" in str(relative)
    ):
        raise GcEvidenceError("invalid_asset_path")
    directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in parts[:-1]:
            child = os.open(
                part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory
            )
            os.close(directory)
            directory = child
        yield directory, parts[-1]
    finally:
        os.close(directory)


class GcFileStorage:
    def __init__(self, roots, *, timeout=5, thumbnail_root=None):
        self.roots = {kind: Path(path).resolve() for kind, path in roots.items()}
        if set(self.roots) != {"cover", "avatar", "video"}:
            raise ValueError("Invalid asset roots")
        values = list(self.roots.values())
        if any(
            left == right or left in right.parents or right in left.parents
            for index, left in enumerate(values)
            for right in values[index + 1 :]
        ):
            raise ValueError("Overlapping asset roots")
        self.timeout = timeout
        self.thumbnail_root = (
            Path(thumbnail_root).resolve()
            if thumbnail_root
            else self.roots["cover"] / "thumbnails"
        )

    @contextmanager
    def locked(self, intent):
        avid = normalize_avid(intent.pool.canonical_avid)
        if avid != intent.pool.canonical_avid:
            raise GcEvidenceError("invalid_pool_identity")
        versions = (
            ResourceVersion.objects.filter(pool_id=intent.pool_id)
            .exclude(state="reclaimed")
            .select_related("work")
        )
        if intent.version_id:
            versions = versions.filter(pk=intent.version_id)
        versions = list(versions.order_by("pk")[:65])
        if len(versions) > 64:
            raise GcDeferred(["version_batch_limit"])
        targets = [
            (asset["root"], asset["relative_path"])
            for version in versions
            for asset in manifest_assets(version)
        ]
        if len(targets) > 1024:
            raise GcDeferred(["asset_batch_limit"])
        job_ids = {
            str(version.work.job_id)
            for version in versions
            if version.work_id is not None
        }
        live = list(
            TaskJob.objects.filter(avid=avid)
            .exclude(state__in=TERMINAL_STATES)
            .values_list("pk", flat=True)[:129]
        )
        if len(live) > 128:
            raise GcDeferred(["writer_batch_limit"])
        job_ids.update(str(value) for value in live)
        base = self.roots["cover"].parent
        with ExitStack() as locks:
            for job_id in sorted(job_ids):
                locks.enter_context(
                    file_lock(
                        base / ".nassav-task-locks" / f"{UUID(job_id)}.lock",
                        timeout=self.timeout,
                    )
                )
            locks.enter_context(
                resource_file_lock(avid, self.roots["cover"], timeout=self.timeout)
            )
            if intent.version_id is None:
                legacy = [
                    self.roots["cover"] / f"{avid}{suffix}"
                    for suffix in (".jpg", ".jpeg", ".png", ".webp", ".html")
                ]
                legacy.append(self.roots["video"] / f"{avid}.mp4")
                legacy.extend(
                    self.thumbnail_root / size / f"{avid}.jpg"
                    for size in ("small", "medium", "large")
                )
                if any(path.exists() or path.is_symlink() for path in legacy):
                    raise GcDeferred(["legacy_assets_unmapped"])
            for root, path in sorted(set(targets)):
                key = hashlib.sha256(f"{root}:{path}".encode()).hexdigest()
                locks.enter_context(
                    file_lock(
                        base / ".nassav-task-target-locks" / f"{key}.lock",
                        timeout=self.timeout,
                    )
                )
            yield

    @contextmanager
    def deletion(self, asset, check):
        path = PurePosixPath(asset["relative_path"])
        if (
            path.parts[:2] != ("versions", str(asset["version_id"]))
            or len(path.parts) < 3
        ):
            raise GcEvidenceError("invalid_asset_path")
        root = self.roots[asset["root"]]
        with ExitStack() as opened:
            try:
                directory, name = opened.enter_context(
                    parent_directory(root, asset["relative_path"])
                )
                fd = os.open(
                    name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory
                )
            except FileNotFoundError:
                if asset["state"] != "verified":
                    raise GcEvidenceError("asset_missing_unverified") from None
                yield None, lambda: None
                return
            try:
                handle = os.fdopen(fd, "rb")
            except BaseException:
                os.close(fd)
                raise
            opened.callback(handle.close)
            initial = os.fstat(handle.fileno())
            if not stat.S_ISREG(initial.st_mode) or initial.st_size != asset["size"]:
                raise GcEvidenceError("asset_identity_changed")
            before = fingerprint(initial)
            digest = hashlib.sha256()
            next_check = 0
            consumed = 0
            for chunk in iter(lambda: handle.read(65536), b""):
                consumed += len(chunk)
                if consumed > asset["size"]:
                    raise GcEvidenceError("asset_identity_changed")
                if time.monotonic() >= next_check:
                    check()
                    next_check = time.monotonic() + 1
                digest.update(chunk)
            check()
            if (
                fingerprint(os.fstat(handle.fileno())) != before
                or digest.hexdigest() != asset["sha256"]
            ):
                raise GcEvidenceError("asset_hash_changed")

            def remove():
                try:
                    current = os.stat(name, dir_fd=directory, follow_symlinks=False)
                except FileNotFoundError:
                    return  # The committed verified journal proves ownership.
                if fingerprint(current) != before:
                    raise GcEvidenceError("asset_identity_changed")
                os.unlink(name, dir_fd=directory)

            yield before, remove

    def clean_namespaces(self, versions, check):
        directories = set()
        for asset in ResourceGcAsset.objects.filter(
            version_id__in=versions, state="deleted"
        ).values("root", "relative_path", "version_id"):
            path = PurePosixPath(asset["relative_path"])
            prefix = ("versions", str(asset["version_id"]))
            if path.parts[:2] != prefix:
                raise GcEvidenceError("invalid_asset_path")
            for parent in path.parents:
                if len(parent.parts) >= 2:
                    directories.add((asset["root"], parent.as_posix()))
        for version_id in versions:
            for kind in self.roots:
                directories.add((kind, f"versions/{UUID(str(version_id))}"))
        for kind, relative in sorted(
            directories, key=lambda item: (-len(PurePosixPath(item[1]).parts), item)
        ):
            check()
            root = self.roots[kind]
            try:
                with parent_directory(root, f"{relative}/entry") as (directory, _):
                    with os.scandir(directory) as entries:
                        if next(entries, None) is not None:
                            raise GcEvidenceError("unregistered_version_files")
                with parent_directory(root, relative) as (parent, name):
                    os.rmdir(name, dir_fd=parent)
            except FileNotFoundError:
                pass
