"""Shared file and ORM boundary for resource and video deletion."""

import re
import shutil
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from loguru import logger

from nassav.models import AVResource
from nassav.signals import resource_deleted
from nassav.resource_file_locks import resource_file_lock


@dataclass(frozen=True)
class DeletionResult:
    found: bool
    resource: dict | None = None
    deleted_files: tuple[str, ...] = ()
    file_size: int | None = None


class InvalidResourceIdentifier(ValueError):
    """An AVID cannot safely be used as a resource path component."""


class ResourceTaskConflict(RuntimeError):
    """A reserved task must be terminated before deleting its resource."""


class ResourceDeletionFailure(Exception):
    """A deletion stopped after some operations may already have completed."""

    def __init__(self, stage: str, deleted_files: list[str]):
        self.stage = stage
        self.deleted_files = tuple(deleted_files)
        super().__init__(f"resource deletion failed during {stage}")


class ResourceDeletionRepository(ABC):
    """Database operations used by the deletion workflow."""

    @abstractmethod
    def get(self, avid: str) -> AVResource | None: ...

    @abstractmethod
    def delete(self, resource: AVResource) -> None: ...

    @abstractmethod
    def clear_video_state(self, avid: str) -> None: ...


class DjangoResourceDeletionRepository(ResourceDeletionRepository):
    def get(self, avid: str) -> AVResource | None:
        from nassav.task_models import TaskJob

        if TaskJob.objects.filter(avid=avid, active_key__isnull=False).exists():
            raise ResourceTaskConflict("资源有运行或暂停的任务，请先终止任务")
        return AVResource.objects.filter(avid=avid).first()

    def delete(self, resource: AVResource) -> None:
        resource.delete()

    def clear_video_state(self, avid: str) -> None:
        AVResource.objects.filter(avid=avid).update(
            file_exists=False, file_size=None, video_saved_at=None
        )


class ResourceDeletionService:
    """Delete a resource or its video and report only confirmed file removals."""

    def __init__(self, repository: ResourceDeletionRepository | None = None):
        self.repository = repository or DjangoResourceDeletionRepository()

    @staticmethod
    def normalize_avid(avid: str) -> str:
        if not isinstance(avid, str):
            raise InvalidResourceIdentifier("invalid avid")
        normalized = avid.strip().upper()
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9._-]*", normalized) or ".." in normalized:
            raise InvalidResourceIdentifier("invalid avid")
        return normalized

    @staticmethod
    def _lock(avid: str):
        return resource_file_lock(avid, Path(settings.COVER_DIR))

    @staticmethod
    def _file_candidates(avid: str) -> list[tuple[Path, str]]:
        cover_dir = Path(settings.COVER_DIR)
        thumb_dir = Path(getattr(settings, "THUMBNAIL_DIR", cover_dir / "thumbnails"))
        video_dir = Path(settings.VIDEO_DIR)
        candidates = [
            (cover_dir / f"{avid}{ext}", f"{avid}{ext}")
            for ext in (".jpg", ".jpeg", ".png", ".webp", ".html")
        ]
        candidates.extend(
            (thumb_dir / size / f"{avid}.jpg", f"thumbnail/{size}/{avid}.jpg")
            for size in ("small", "medium", "large")
        )
        candidates.append((video_dir / f"{avid}.mp4", f"{avid}.mp4"))
        return candidates

    @staticmethod
    def _backup_dir(avid: str) -> Path:
        return (
            Path(
                getattr(
                    settings,
                    "RESOURCE_BACKUP_DIR",
                    Path(settings.BASE_DIR) / "resource_backup",
                )
            )
            / avid
        )

    def delete_resource(
        self,
        avid: str,
        *,
        include_files: bool = True,
        serialize: Callable[[AVResource], dict] | None = None,
    ) -> DeletionResult:
        avid = self.normalize_avid(avid)
        with self._lock(avid):
            resource = self.repository.get(avid)
            candidates = self._file_candidates(avid) if include_files else []
            backup_dir = self._backup_dir(avid) if include_files else None
            found_files = any(path.exists() for path, _ in candidates) or bool(
                backup_dir and backup_dir.exists()
            )
            if resource is None and not found_files:
                return DeletionResult(found=False)

            resource_data = serialize(resource) if resource and serialize else None
            deleted: list[str] = []
            try:
                for path, label in candidates:
                    if path.exists():
                        path.unlink()
                        deleted.append(label)
                if backup_dir and backup_dir.exists():
                    names = [path.name for path in backup_dir.iterdir()]
                    shutil.rmtree(backup_dir)
                    deleted.extend(names)
            except Exception as exc:
                logger.exception("Resource {} file deletion failed", avid)
                raise ResourceDeletionFailure("files", deleted) from exc

            if resource is not None:
                try:
                    self.repository.delete(resource)
                except Exception as exc:
                    logger.exception("Resource {} database deletion failed", avid)
                    raise ResourceDeletionFailure("database", deleted) from exc
                try:
                    resource_deleted.send(
                        sender=self.__class__, avid=avid, delete_files=include_files
                    )
                except Exception:
                    logger.exception("Resource {} deletion signal failed", avid)
            return DeletionResult(True, resource_data, tuple(deleted))

    def delete_video(self, avid: str) -> DeletionResult:
        avid = self.normalize_avid(avid)
        with self._lock(avid):
            path = Path(settings.VIDEO_DIR) / f"{avid}.mp4"
            resource = self.repository.get(avid)
            stale_state = bool(
                resource
                and (
                    resource.file_exists
                    or resource.file_size
                    or resource.video_saved_at
                )
            )
            if not path.exists() and not stale_state:
                return DeletionResult(found=False)
            deleted: list[str] = []
            file_size = None
            try:
                if path.exists():
                    file_size = path.stat().st_size
                    path.unlink()
                    deleted.append(path.name)
            except Exception as exc:
                logger.exception("Resource {} video deletion failed", avid)
                raise ResourceDeletionFailure("files", deleted) from exc
            try:
                if resource:
                    self.repository.clear_video_state(avid)
            except Exception as exc:
                logger.exception("Resource {} video state update failed", avid)
                raise ResourceDeletionFailure("database", deleted) from exc
            return DeletionResult(
                True, deleted_files=tuple(deleted), file_size=file_size
            )


resource_deletion_service = ResourceDeletionService()
