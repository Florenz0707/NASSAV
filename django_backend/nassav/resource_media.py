"""Cover selection, freshness and thumbnail generation behind a single locator."""

import mimetypes
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


class InvalidThumbnailSize(ValueError):
    pass


@dataclass(frozen=True)
class LocatedCover:
    path: Path
    content_type: str
    etag: str | None = None


class CoverLocator(ABC):
    @abstractmethod
    def locate(self, avid: str, size: str | None = None) -> LocatedCover | None: ...


class FileCoverLocator(CoverLocator):
    SIZES = {"small": 200, "medium": 600, "large": 1200}

    def __init__(
        self, covers: Path, thumbnails: Path, thumbnailer: Callable, etag: Callable
    ):
        self.covers, self.thumbnails, self.thumbnailer, self.etag = (
            covers,
            thumbnails,
            thumbnailer,
            etag,
        )

    def locate(self, avid: str, size: str | None = None) -> LocatedCover | None:
        original = next(
            (
                self.covers / f"{avid}{ext}"
                for ext in (".jpg", ".jpeg", ".png", ".webp")
                if (self.covers / f"{avid}{ext}").exists()
            ),
            None,
        )
        if original is None:
            return None
        content_type = (
            mimetypes.guess_type(str(original))[0] or "application/octet-stream"
        )
        if not size:
            try:
                etag = self.etag(original)
            except Exception:
                etag = '"0"'
            return LocatedCover(original, content_type, etag)
        size = str(size).lower()
        if size not in self.SIZES:
            raise InvalidThumbnailSize("size 参数无效，支持 small|medium|large")
        thumbnail = self.thumbnails / size / f"{avid}.jpg"
        try:
            if (
                thumbnail.exists()
                and thumbnail.stat().st_mtime >= original.stat().st_mtime
            ):
                return LocatedCover(thumbnail, "image/jpeg", self.etag(thumbnail))
        except Exception:
            pass
        success = self.thumbnailer(original, thumbnail, self.SIZES[size])
        if success and thumbnail.exists():
            return LocatedCover(thumbnail, "image/jpeg")
        return LocatedCover(original, content_type)
