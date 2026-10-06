"""Owned task workspaces, journaled publication and retryable private cleanup."""

import errno
import hashlib
import os
import shutil
import stat
from collections.abc import Callable, Mapping, Sequence
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from uuid import UUID, uuid4

from nassav.resource_file_locks import file_lock, resource_file_lock
from nassav.task_control_rules import (
    ExecutionToken,
    TaskExecutionInvalid,
    TERMINAL_STATES,
)
from nassav.task_models import TaskArtifact, TaskAssetTarget, TaskAttempt
from nassav.task_records import DjangoTaskRecords


class TaskAssetError(RuntimeError):
    pass


class TaskAssetRecoveryRequired(TaskAssetError):
    pass


@dataclass(frozen=True)
class AssetPromotion:
    artifact_id: int
    target_path: str
    reuse_existing: bool = False
    reuse_if: Callable[[Path], bool] | None = None


def _relative(value: str) -> str:
    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or "\\" in value
        or any(ord(c) < 32 for c in value)
        or any(part in {"", ".", ".."} for part in value.split("/"))
    ):
        raise ValueError("无效的资产相对路径")
    return str(path)


def _sha(path: Path, check: Callable | None = None) -> str:
    hasher = hashlib.sha256()
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            if check:
                check()
            hasher.update(chunk)
    return hasher.hexdigest()


def _snapshot_existing(target: Path, backup: Path, expected_hash: str, check: Callable):
    """Prefer cheap links; copy readable legacy files when linking is prohibited."""
    check()
    try:
        os.link(target, backup, follow_symlinks=False)
    except OSError as error:
        if error.errno not in {
            errno.EPERM,
            errno.EACCES,
            errno.EXDEV,
            errno.EOPNOTSUPP,
        }:
            raise
        partial = backup.with_name(backup.name + ".copy")
        try:
            with os.fdopen(
                os.open(target, os.O_RDONLY | os.O_NOFOLLOW), "rb"
            ) as source:
                info = os.fstat(source.fileno())
                if not stat.S_ISREG(info.st_mode):
                    raise TaskAssetError("旧资产不是普通文件")
                with os.fdopen(
                    os.open(
                        partial,
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                        0o600,
                    ),
                    "wb",
                ) as destination:
                    for chunk in iter(lambda: source.read(1024 * 1024), b""):
                        check()
                        destination.write(chunk)
                    destination.flush()
                    os.fsync(destination.fileno())
                    os.fchmod(destination.fileno(), stat.S_IMODE(info.st_mode) & 0o777)
                os.utime(
                    partial,
                    ns=(info.st_atime_ns, info.st_mtime_ns),
                    follow_symlinks=False,
                )
            if _sha(partial, check) != expected_hash:
                raise TaskAssetRecoveryRequired("旧文件备份校验不一致")
            check()
            os.replace(partial, backup)
            return
        finally:
            partial.unlink(missing_ok=True)
    if _sha(backup, check) != expected_hash:
        raise TaskAssetRecoveryRequired("旧文件备份校验不一致")


def _fingerprint(path: Path) -> tuple:
    if not path.exists():
        return ()
    info = path.stat(follow_symlinks=False)
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


class TaskAssets:
    def __init__(self, roots: Mapping[str, Path], records: DjangoTaskRecords):
        self.roots = {key: value.resolve() for key, value in roots.items()}
        if set(self.roots) != {"cover", "avatar", "video"}:
            raise ValueError("资产根必须包含 cover/avatar/video")
        values = list(self.roots.values())
        if any(
            left == right or left in right.parents or right in left.parents
            for index, left in enumerate(values)
            for right in values[index + 1 :]
        ):
            raise ValueError("资产根不能相同或互相嵌套")
        self.records = records

    def _path(self, root: str, relative: str, *, parents: bool = False) -> Path:
        if root not in self.roots:
            raise ValueError("未知资产根")
        relative = _relative(relative)
        base = self.roots[root]
        base.mkdir(parents=True, exist_ok=True)
        current = base
        parts = PurePosixPath(relative).parts
        for index, part in enumerate(parts):
            current = current / part
            if current.is_symlink():
                raise TaskAssetError("资产路径包含符号链接")
            if parents and index < len(parts) - 1:
                current.mkdir(exist_ok=True)
        return current

    @staticmethod
    def _private(job_id: str, relative: str) -> str:
        return f".tasks/{UUID(job_id)}/{_relative(relative)}"

    @contextmanager
    def _locks(self, job_id: str, targets: Sequence[tuple[str, str]] = ()):
        job = self.records.get(job_id)
        base = self.roots["cover"].parent
        with ExitStack() as stack:
            stack.enter_context(
                file_lock(base / ".nassav-task-locks" / f"{UUID(job_id)}.lock")
            )
            stack.enter_context(resource_file_lock(job["avid"], self.roots["cover"]))
            for root, target in sorted(set(targets)):
                key = hashlib.sha256(f"{root}:{target}".encode()).hexdigest()
                stack.enter_context(
                    file_lock(base / ".nassav-task-target-locks" / f"{key}.lock")
                )
            yield

    def workspace(
        self, token: ExecutionToken, root: str, relative: str = "download"
    ) -> Path:
        """Reserve the directory before CLI output; cleanup owns all its descendants."""
        self.records.check(token)
        if TaskArtifact.objects.filter(job_id=token.job_id, state="promoting").exists():
            raise TaskAssetRecoveryRequired("需要先恢复未完成提交")
        path = self._path(root, self._private(token.job_id, relative), parents=True)
        self.records.controlled_transaction(
            token,
            lambda: TaskArtifact.objects.get_or_create(
                job_id=token.job_id,
                root=root,
                relative_path=_relative(relative),
                defaults={"kind": "workspace"},
            ),
        )
        path.mkdir(exist_ok=True)
        self.records.check(token)
        return path

    def stage(
        self,
        token: ExecutionToken,
        root: str,
        relative: str,
        kind: str,
        producer: Callable[[Path], bool],
        *,
        validate: Callable[[Path], bool] | None = None,
        check: Callable | None = None,
    ) -> int:
        self.records.check(token)
        path = self._path(root, self._private(token.job_id, relative), parents=True)
        artifact, _ = self.records.controlled_transaction(
            token,
            lambda: TaskArtifact.objects.get_or_create(
                job_id=token.job_id,
                root=root,
                relative_path=_relative(relative),
                defaults={"kind": kind},
            ),
        )
        if artifact.state != "staged":
            raise TaskAssetError("已提交或待恢复的资产不得重复写入")
        produced = producer(path)
        path = self._path(root, self._private(token.job_id, relative))
        if not produced or not path.is_file() or not path.stat().st_size:
            raise TaskAssetError("资产生成未完成")
        if validate and not validate(path):
            raise TaskAssetError("资产内容校验失败")
        # A completed private file can be recorded before acknowledging a pending stop.
        size, checksum = path.stat().st_size, _sha(path, check)
        self.records.controlled_transaction(
            token,
            lambda: TaskArtifact.objects.filter(pk=artifact.pk, state="staged").update(
                size=size, sha256=checksum, details={"complete": True}
            ),
            allow_stopping=True,
        )
        self.records.check(token)
        return artifact.pk

    def _source(self, artifact: TaskArtifact) -> Path:
        return self._path(
            artifact.root,
            self._private(str(artifact.job_id), artifact.relative_path),
            parents=True,
        )

    def completed(self, token: ExecutionToken, root: str, relative: str) -> int | None:
        """Reuse only an owned, complete private file with the recorded checksum."""
        self.records.check(token)
        artifact = TaskArtifact.objects.filter(
            job_id=token.job_id,
            root=root,
            relative_path=_relative(relative),
            state="staged",
        ).first()
        if artifact is None or not artifact.details.get("complete"):
            return None
        path = self._source(artifact)
        if (
            not path.is_file()
            or _sha(path, lambda: self.records.check(token)) != artifact.sha256
        ):
            raise TaskAssetError("检查点文件损坏，不能复用")
        return artifact.pk

    def read(self, token: ExecutionToken, root: str, relative: str) -> bytes:
        artifact_id = self.completed(token, root, relative)
        if artifact_id is None:
            raise TaskAssetError("检查点文件尚未完成")
        artifact = TaskArtifact.objects.get(pk=artifact_id)
        if artifact.size is None or artifact.size > 16 * 1024 * 1024:
            raise TaskAssetError("检查点文件超出读取上限")
        return self._source(artifact).read_bytes()

    def valid_existing(
        self, root: str, relative: str, validate: Callable[[Path], bool]
    ) -> bool:
        path = self._path(root, relative)
        return path.is_file() and validate(path)

    def _backup(self, artifact: TaskArtifact) -> Path:
        return self._path(
            artifact.root,
            self._private(str(artifact.job_id), artifact.details["backup"]),
            parents=True,
        )

    def commit(
        self,
        token: ExecutionToken,
        promotions: Sequence[AssetPromotion],
        persist: Callable,
        *,
        resource_saved: bool = False,
        checkpoint: dict | Callable | None = None,
    ):
        """Journal then fence a short file/ORM commit; no HTTP or dispatch in persist."""
        ids = [promotion.artifact_id for promotion in promotions]
        artifacts = list(TaskArtifact.objects.filter(job_id=token.job_id, pk__in=ids))
        if len(set(ids)) != len(ids) or len(artifacts) != len(ids):
            raise TaskAssetError("提交清单不属于此任务或包含重复项")
        by_id = {artifact.pk: artifact for artifact in artifacts}
        targets = []
        for promotion in promotions:
            target = _relative(promotion.target_path)
            if target == ".tasks" or target.startswith(".tasks/"):
                raise ValueError("正式目标不能是任务工作区")
            targets.append((by_id[promotion.artifact_id].root, target))
        if len(set(targets)) != len(targets):
            raise TaskAssetError("正式目标重复")
        commit_id = str(uuid4())
        with self._locks(token.job_id, targets):
            # Hash large videos outside the DB write fence so commands stay responsive.
            checked = {}
            for promotion in promotions:
                artifact = by_id[promotion.artifact_id]
                source = self._source(artifact)
                target = self._path(artifact.root, promotion.target_path, parents=True)
                source_stat, target_stat = _fingerprint(source), _fingerprint(target)
                checksum = _sha(source, lambda: self.records.check(token))
                old_hash = (
                    _sha(target, lambda: self.records.check(token))
                    if target.is_file()
                    else ""
                )
                if source_stat != _fingerprint(source) or target_stat != _fingerprint(
                    target
                ):
                    raise TaskAssetError("提交校验期间文件变化")
                checked[artifact.pk] = (checksum, old_hash, source_stat, target_stat)

            def prepare():
                for promotion in promotions:
                    artifact = by_id[promotion.artifact_id]
                    artifact.refresh_from_db()
                    source = self._source(artifact)
                    if (
                        artifact.state != "staged"
                        or not artifact.sha256
                        or checked[artifact.pk][0] != artifact.sha256
                        or _fingerprint(source) != checked[artifact.pk][2]
                    ):
                        raise TaskAssetError("提交前资产校验不一致")
                    target = self._path(
                        artifact.root, promotion.target_path, parents=True
                    )
                    old_hash = checked[artifact.pk][1]
                    if _fingerprint(target) != checked[artifact.pk][3]:
                        raise TaskAssetError("正式文件在提交前变化")
                    epoch, _ = TaskAssetTarget.objects.get_or_create(
                        root=artifact.root,
                        relative_path=promotion.target_path,
                        defaults={"sha256": old_hash},
                    )
                    artifact.target_path = promotion.target_path
                    artifact.state = "promoting"
                    artifact.details = {
                        **artifact.details,
                        "commit_id": commit_id,
                        "old_marker": str(epoch.marker),
                        "new_marker": str(uuid4()),
                        "old_sha256": old_hash,
                        "backup": f"rollback/{commit_id}/{artifact.pk}",
                        "reuse": promotion.reuse_existing
                        and target.is_file()
                        and (promotion.reuse_if is None or promotion.reuse_if(target)),
                    }
                    artifact.save(
                        update_fields=["target_path", "state", "details", "updated_at"]
                    )

            self.records.controlled_transaction(
                token, prepare, checkpoint={"preparing_commit": commit_id}
            )
            try:
                # Backup IO stays outside the DB fence, including legacy-file copies.
                # Durable preparation already names the backup for crash recovery.
                for artifact in artifacts:
                    artifact.refresh_from_db()
                    if artifact.details["reuse"] or not artifact.details["old_sha256"]:
                        continue
                    self.records.check(token)
                    target = self._path(artifact.root, artifact.target_path)
                    previous = checked[artifact.pk]
                    if _fingerprint(target) != previous[3]:
                        raise TaskAssetRecoveryRequired("正式文件在备份前变化")
                    _snapshot_existing(
                        target,
                        self._backup(artifact),
                        previous[1],
                        lambda: self.records.check(token),
                    )
                    current = _fingerprint(target)
                    if not current or current[:3] != previous[3][:3]:
                        raise TaskAssetRecoveryRequired("正式文件在备份期间变化")
                    # A hard link changes ctime; subsequent publication uses this snapshot.
                    checked[artifact.pk] = (*previous[:3], current)

                def publish():
                    for artifact in artifacts:
                        artifact.refresh_from_db()
                        target = self._path(
                            artifact.root, artifact.target_path, parents=True
                        )
                        source = self._source(artifact)
                        epoch = TaskAssetTarget.objects.get(
                            root=artifact.root, relative_path=artifact.target_path
                        )
                        if str(epoch.marker) != artifact.details["old_marker"]:
                            raise TaskAssetRecoveryRequired("正式资产归属已经变化")
                        if (
                            _fingerprint(source) != checked[artifact.pk][2]
                            or _fingerprint(target) != checked[artifact.pk][3]
                        ):
                            raise TaskAssetRecoveryRequired(
                                "正式或暂存文件在提交期间变化"
                            )
                        if not artifact.details["reuse"]:
                            os.replace(source, target)
                            epoch.marker = UUID(artifact.details["new_marker"])
                            epoch.sha256 = artifact.sha256
                            epoch.save(update_fields=["marker", "sha256", "updated_at"])
                        artifact.state = "committed"
                        artifact.save(update_fields=["state", "updated_at"])
                    return persist()

                return self.records.controlled_transaction(
                    token,
                    publish,
                    checkpoint=lambda result: {
                        "last_commit": commit_id,
                        "preparing_commit": None,
                        **(
                            (checkpoint(result) if callable(checkpoint) else checkpoint)
                            or {}
                        ),
                    },
                    resource_saved=resource_saved,
                )
            except BaseException:
                # The DB transaction rolled back; the durable preparation journal remains.
                self._rollback(
                    list(TaskArtifact.objects.filter(pk__in=ids, state="promoting"))
                )
                raise

    def _rollback(self, artifacts: Sequence[TaskArtifact]) -> None:
        for artifact in artifacts:
            if artifact.details.get("reuse"):
                artifact.state = "staged"
                artifact.save(update_fields=["state", "updated_at"])
                continue
            target = self._path(artifact.root, artifact.target_path, parents=True)
            backup, source = self._backup(artifact), self._source(artifact)
            epoch = TaskAssetTarget.objects.get(
                root=artifact.root, relative_path=artifact.target_path
            )
            if str(epoch.marker) != artifact.details["old_marker"]:
                raise TaskAssetRecoveryRequired("后续任务已提交，拒绝回滚其正式文件")
            current_hash = _sha(target) if target.is_file() else ""
            if current_hash not in {
                artifact.sha256,
                artifact.details["old_sha256"],
                "",
            }:
                raise TaskAssetRecoveryRequired("正式文件内容不再属于此提交")
            old_hash = artifact.details["old_sha256"]
            if backup.exists():
                if _sha(backup) != old_hash:
                    raise TaskAssetRecoveryRequired("旧文件备份校验不一致")
            # Source presence tells whether replace happened, including identical bytes.
            published = not source.exists()
            if published:
                if current_hash != artifact.sha256 or (
                    old_hash and not backup.exists()
                ):
                    raise TaskAssetRecoveryRequired("提交恢复缺少已验证文件或旧备份")
                os.replace(target, source)
            elif _sha(source) != artifact.sha256 or current_hash not in {old_hash, ""}:
                raise TaskAssetRecoveryRequired("文件变化不属于此提交")
            if backup.exists():
                if published or not target.exists():
                    os.replace(backup, target)
                else:
                    # Backup completed but publication never started: preserve old inode.
                    backup.unlink()
            elif old_hash and not target.exists():
                raise TaskAssetRecoveryRequired("旧文件备份缺失")
            artifact.state = "staged"
            artifact.save(update_fields=["state", "updated_at"])

    def recover(self, job_id: str) -> None:
        """Only called after execution exit is established, never on heartbeat expiry alone."""
        if TaskAttempt.objects.filter(job_id=job_id, state="running").exists():
            raise TaskExecutionInvalid("执行未确认退出，拒绝恢复文件")
        artifacts = list(TaskArtifact.objects.filter(job_id=job_id, state="promoting"))
        with self._locks(
            job_id, [(artifact.root, artifact.target_path) for artifact in artifacts]
        ):
            self.records.stopped_transaction(job_id, lambda: self._rollback(artifacts))

    def cleanup(self, job_id: str) -> dict:
        """Remove only this job's private roots, preserving every published asset."""
        job = self.records.get(job_id)
        if (
            job["state"] not in TERMINAL_STATES
            or TaskAttempt.objects.filter(job_id=job_id, state="running").exists()
        ):
            raise TaskExecutionInvalid("停止确认前不能清理")
        self.records.set_cleanup(job_id, "running")
        try:
            self.recover(job_id)
            with self._locks(job_id):
                for root in self.roots:
                    private = self._path(root, f".tasks/{UUID(job_id)}")
                    if private.exists():
                        # shutil's Linux fd-based implementation does not traverse symlinks.
                        if not shutil.rmtree.avoids_symlink_attacks:
                            raise TaskAssetError("当前平台不支持安全目录清理")
                        shutil.rmtree(private)
                TaskArtifact.objects.filter(job_id=job_id).exclude(
                    state="committed"
                ).update(state="deleted")
            return self.records.set_cleanup(job_id, "completed")
        except Exception as error:
            return self.records.set_cleanup(job_id, "failed", str(error)[:200])
