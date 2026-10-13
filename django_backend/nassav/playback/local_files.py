"""Published MP4 locator: no upstream access and no private task assets."""

import os
import stat
import threading
from pathlib import Path
from nassav.models import AVResource
from nassav.task_models import TaskArtifact, TaskAssetTarget
from nassav.resource_file_locks import resource_file_lock
from nassav.task_control_rules import normalize_avid
from .policy import PlaybackGatewayError


def fingerprint(value):
    return [
        value.st_dev,
        value.st_ino,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    ]


class LocalVideo:
    def __init__(self, fd):
        self.fd = fd
        self.lock = threading.Lock()

    def read(self, offset, size):
        with self.lock:
            if self.fd is None:
                raise PlaybackGatewayError("local_media_unavailable", 410)
            return os.pread(self.fd, size, offset)

    def close(self):
        with self.lock:
            if self.fd is not None:
                os.close(self.fd)
                self.fd = None


class DjangoLocalVideoLocator:
    def __init__(self, video_root, cover_root):
        # Resolve the configured root, allowing the documented deployment symlink.
        self.root, self.cover_root = (
            Path(video_root).resolve(),
            Path(cover_root).resolve(),
        )

    def path(self, avid):
        try:
            if normalize_avid(avid) != avid:
                raise ValueError("Invalid identity")
        except ValueError as error:
            raise PlaybackGatewayError("invalid_resource_identity", 400) from error
        return self.root / f"{avid}.mp4"

    def identity(self, avid):
        path = self.path(avid)
        if not AVResource.objects.filter(avid=avid, file_exists=True).exists():
            raise PlaybackGatewayError("local_video_not_found", 404)
        if TaskArtifact.objects.filter(
            root="video", target_path=path.name, state="promoting"
        ).exists():
            raise PlaybackGatewayError("local_publication_pending", 409)
        marker = (
            TaskAssetTarget.objects.filter(root="video", relative_path=path.name)
            .values_list("marker", flat=True)
            .first()
        )
        return self._file_identity(avid, marker)

    def _file_identity(self, avid, marker):
        try:
            value = self.path(avid).lstat()
        except FileNotFoundError:
            raise PlaybackGatewayError("local_video_not_found", 404)
        if not stat.S_ISREG(value.st_mode) or value.st_size <= 0:
            raise PlaybackGatewayError("local_video_rejected", 422)
        return {
            "schema": "local-playback-v1",
            "fingerprint": fingerprint(value),
            "marker": str(marker) if marker else None,
        }

    def identities(self, avids):
        """Batch database facts and bounded stat checks for display-only projection.

        Session creation still locks and revalidates the publication independently.
        """
        if not avids:
            return {}
        existing = set(
            AVResource.objects.filter(avid__in=avids, file_exists=True).values_list(
                "avid", flat=True
            )
        )
        names = {f"{avid}.mp4" for avid in existing}
        pending = set(
            TaskArtifact.objects.filter(
                root="video", target_path__in=names, state="promoting"
            ).values_list("target_path", flat=True)
        )
        markers = dict(
            TaskAssetTarget.objects.filter(
                root="video", relative_path__in=names
            ).values_list("relative_path", "marker")
        )
        result = {}
        for avid in existing:
            name = f"{avid}.mp4"
            if name in pending:
                continue
            try:
                result[avid] = self._file_identity(avid, markers.get(name))
            except (PlaybackGatewayError, OSError):
                # Unavailable, invalid or racing files cannot offer continuation.
                continue
        return result

    def locked(self, avid):
        self.path(avid)  # Validate before constructing a lock path.
        return resource_file_lock(avid, self.cover_root, timeout=5)

    def check(self, avid, expected):
        try:
            current = self.identity(avid)
        except PlaybackGatewayError as error:
            if error.status == 404:
                raise PlaybackGatewayError("local_media_removed", 410) from error
            raise
        if current != expected:
            raise PlaybackGatewayError("media_identity_changed", 410)

    def open(self, avid, expected):
        try:
            with self.locked(avid):
                self.check(avid, expected)
                # Final file symlinks are forbidden, including a raced replacement.
                fd = os.open(
                    self.path(avid), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
                )
                try:
                    value = os.fstat(fd)
                    if (
                        not stat.S_ISREG(value.st_mode)
                        or fingerprint(value) != expected["fingerprint"]
                    ):
                        raise PlaybackGatewayError("media_identity_changed", 410)
                    return LocalVideo(fd)
                except BaseException:
                    os.close(fd)
                    raise
        except TimeoutError as error:
            raise PlaybackGatewayError("local_video_busy", 409) from error
        except OSError as error:
            raise PlaybackGatewayError("local_media_unavailable", 410) from error


def submit_local(locator, store, user_id, key, avid, request_id):
    # An idempotent retry must not bind to a later publication under the same key.
    previous = (
        store.PlaybackSession.objects.filter(
            user_id=user_id, login_hash=store.login_hash(key), request_id=request_id
        )
        .select_related("resource")
        .first()
    )
    if previous:
        if previous.resource.avid != avid or previous.media_kind != "local":
            raise ValueError("Request identity conflict")
        return previous
    try:
        with locator.locked(avid):
            descriptor = locator.identity(avid)
            return store.submit(
                user_id, key, avid, request_id, mode="local", descriptor=descriptor
            )
    except TimeoutError as error:
        raise PlaybackGatewayError("local_video_busy", 409) from error
