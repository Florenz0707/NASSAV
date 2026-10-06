#!/usr/bin/env python3
"""Check or repair explicitly selected backend runtime paths while writers are stopped."""

import argparse
import json
import os
import stat
from pathlib import Path

RUNTIME_DIRS = (
    "config",
    "db",
    "log",
    "resource_backup",
    "backup",
    "backup_sync",
    "celery_beat",
)
MEDIA_DIRS = ("cover", "avatar", "video", "recommendation_cover")
LOCK_DIRS = (".nassav-delete-locks", ".nassav-task-locks", ".nassav-task-target-locks")


def checked(path: Path):
    for parent in (*reversed(path.parents), path):
        if parent.is_symlink():
            raise ValueError(f"Refusing symlink: {parent}; pass the verified real path")
    if not path.exists():
        return None
    info = path.lstat()
    if not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
        raise ValueError(f"Refusing special file: {path}")
    if stat.S_ISREG(info.st_mode) and info.st_nlink != 1:
        raise ValueError(f"Refusing hard-linked file: {path}")
    return info


def plan(
    data_dir: Path, resource_dir: Path, *, include_published=False
) -> dict[Path, bool]:
    """Directories are True, files False; media migration requires explicit opt-in."""
    entries = {data_dir: True, resource_dir: True}
    trees = [data_dir / name for name in RUNTIME_DIRS]
    for name in MEDIA_DIRS:
        entries[resource_dir / name] = True
        trees.append(resource_dir / name / ".tasks")
    trees.extend(resource_dir / name for name in LOCK_DIRS)
    for root in trees:
        entries[root] = True
        info = checked(root)
        if info is None:
            continue
        if not stat.S_ISDIR(info.st_mode):
            raise ValueError(f"Expected directory: {root}")
        for current, directories, files in os.walk(
            root, followlinks=False, onerror=raise_error
        ):
            for name in directories + files:
                path = Path(current) / name
                info = checked(path)
                if info is None:
                    raise FileNotFoundError(path)
                entries[path] = stat.S_ISDIR(info.st_mode)
    if include_published:
        for name in MEDIA_DIRS:
            root = resource_dir / name
            if checked(root) is None:
                continue
            for current, directories, files in os.walk(
                root, followlinks=False, onerror=raise_error
            ):
                directories[:] = [item for item in directories if item != ".tasks"]
                for item in directories + files:
                    path = Path(current) / item
                    info = checked(path)
                    if info is None:
                        raise FileNotFoundError(path)
                    entries[path] = stat.S_ISDIR(info.st_mode)
    for path, directory in entries.items():
        info = checked(path)
        if info and directory != stat.S_ISDIR(info.st_mode):
            raise ValueError(f"Unexpected path type: {path}")
    return entries


def raise_error(error):
    raise error


def prepare(
    data_dir,
    resource_dir,
    uid,
    gid,
    *,
    repair=False,
    writers_stopped=False,
    include_published=False,
):
    if uid <= 0 or gid <= 0:
        raise ValueError("Use a non-root UID and GID")
    if repair and not writers_stopped:
        raise ValueError(
            "Repair requires --writers-stopped; stop all API/workers and descendants first"
        )
    if any(".." in Path(value).parts for value in (data_dir, resource_dir)):
        raise ValueError("Refusing parent traversal")
    data_dir, resource_dir = Path(data_dir).absolute(), Path(resource_dir).absolute()
    if data_dir == Path("/") or resource_dir == Path("/"):
        raise ValueError("Refusing filesystem root")
    entries = plan(data_dir, resource_dir, include_published=include_published)
    problems = []
    for path, directory in entries.items():
        info = checked(path)
        required = 0o700 if directory else 0o600
        if (
            info is None
            or (info.st_uid, info.st_gid) != (uid, gid)
            or info.st_mode & required != required
        ):
            problems.append(path)
    if repair:
        # Preserve lock inode, file contents and existing group/other permissions.
        for path in sorted(problems, key=lambda item: len(item.parts)):
            info = checked(path)
            if info is None:
                path.mkdir(parents=True, exist_ok=True)
                info = checked(path)
            if info is None:
                raise FileNotFoundError(path)
            os.chown(path, uid, gid, follow_symlinks=False)
            os.chmod(
                path, stat.S_IMODE(info.st_mode) | (0o700 if entries[path] else 0o600)
            )
    return {
        "status": "repaired" if repair else ("needs_repair" if problems else "ok"),
        "uid": uid,
        "gid": gid,
        "checked": len(entries),
        "affected": len(problems),
        "paths": [str(path) for path in problems[:20]],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--resource-dir", required=True, type=Path)
    parser.add_argument("--uid", required=True, type=int)
    parser.add_argument("--gid", required=True, type=int)
    parser.add_argument(
        "--include-published",
        action="store_true",
        help="Also inspect/repair existing published media ownership (offline migration)",
    )
    parser.add_argument("--repair", action="store_true")
    parser.add_argument("--writers-stopped", action="store_true")
    args = parser.parse_args()
    try:
        result = prepare(
            args.data_dir,
            args.resource_dir,
            args.uid,
            args.gid,
            repair=args.repair,
            writers_stopped=args.writers_stopped,
            include_published=args.include_published,
        )
        print(json.dumps(result))
        return 1 if result["status"] == "needs_repair" else 0
    except (OSError, ValueError) as error:
        parser.exit(1, f"Backend permissions failed: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
