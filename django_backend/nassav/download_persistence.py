"""Persist the file state resulting from a video download task."""

from abc import ABC, abstractmethod
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from nassav.models import AVResource


class DownloadPersistence(ABC):
    @abstractmethod
    def mark_completed(self, avid: str) -> None:
        """Reflect the downloaded file in the resource record."""

    @abstractmethod
    def mark_failed(self, avid: str) -> None:
        """Mark a failed download as unavailable."""


class DjangoDownloadPersistence(DownloadPersistence):
    def mark_completed(self, avid: str) -> None:
        mp4_file = Path(settings.VIDEO_DIR) / f"{avid.upper()}.mp4"
        with transaction.atomic():
            if mp4_file.exists():
                AVResource.objects.filter(avid=avid).update(
                    file_exists=True,
                    file_size=mp4_file.stat().st_size,
                    video_saved_at=timezone.now(),
                )
            else:
                AVResource.objects.filter(avid=avid).update(
                    file_exists=False, file_size=None, video_saved_at=None
                )

    def mark_failed(self, avid: str) -> None:
        with transaction.atomic():
            AVResource.objects.filter(avid=avid).update(file_exists=False)


download_persistence = DjangoDownloadPersistence()
