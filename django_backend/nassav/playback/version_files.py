"""Fixed-version MP4 handles; legacy files have an explicit owned fallback."""

import os
import re
import stat
from pathlib import Path, PurePosixPath
from uuid import UUID

from nassav.library_catalog import own_entry, held_entries, version_filter
from nassav.library_membership import LibraryNotFound
from nassav.resource_version_models import ResourceVersion
from nassav.resource_file_locks import resource_file_lock
from nassav.task_control_rules import normalize_avid
from nassav.task_models import TaskAssetTarget, TaskArtifact
from nassav.version_image_files import open_beneath
from .local_files import LocalVideo, fingerprint, DjangoLocalVideoLocator
from .policy import PlaybackGatewayError


class DjangoVersionVideoLocator:
    def __init__(self, video_root, cover_root, user_id, *, version_id=None):
        self.root, self.cover_root = (
            Path(video_root).resolve(),
            Path(cover_root).resolve(),
        )
        self.user_id, self.version_id = user_id, version_id
        self.legacy = DjangoLocalVideoLocator(video_root, cover_root)

    def locked(self, avid):
        try:
            if normalize_avid(avid) != avid:
                raise ValueError("Invalid resource")
        except ValueError:
            raise PlaybackGatewayError("invalid_resource_identity", 400) from None
        return resource_file_lock(avid, self.cover_root, timeout=5)

    def _version(self, avid, expected=None):
        try:
            fixed = self.version_id or (expected or {}).get("version_id")
            if fixed is not None:
                if self.version_id is not None and str(fixed) != str(self.version_id):
                    raise LibraryNotFound("Version mismatch")
                version = (
                    ResourceVersion.objects.select_related("pool")
                    .filter(pk=UUID(str(fixed)), pool__canonical_avid=avid)
                    .first()
                )
                if version is None:
                    raise LibraryNotFound("Version unavailable")
            else:
                version = own_entry(self.user_id, avid=avid).video_version
            if version is None:
                # Only public/legacy ownership can consume an unversioned file.
                entry = own_entry(self.user_id, avid=avid)
                if (
                    entry.access_scope
                    not in {"public", f"legacy:operator:{self.user_id}"}
                    or expected
                    and expected.get("version_id")
                ):
                    raise LibraryNotFound("Version unavailable")
                return None
            if (
                version.kind != "video"
                or version.pool.canonical_avid != avid
                or version.state not in {"ready", "retired"}
                or version.published_at is None
                or not version.pool.is_available
                or version.pool.state not in {"ready", "preparing", "pending_gc"}
                or (version.owner_id is not None and version.owner_id != self.user_id)
            ):
                raise LibraryNotFound("Version unavailable")
            return version
        except (LibraryNotFound, ValueError, TypeError):
            raise PlaybackGatewayError("local_media_removed", 410) from None

    @staticmethod
    def _asset(version):
        if (
            not isinstance(version.manifest, list)
            or len(version.manifest) != 1
            or not isinstance(version.manifest[0], dict)
        ):
            raise PlaybackGatewayError("local_video_rejected", 422)
        asset = version.manifest[0]
        path = asset.get("path")
        if (
            asset.get("root") != "video"
            or asset.get("kind") != "video"
            or not isinstance(path, str)
            or PurePosixPath(path).parts != ("versions", str(version.pk), "video.mp4")
            or "\\" in path
            or path != str(PurePosixPath(path))
            or type(asset.get("size")) is not int
            or asset["size"] <= 0
            or asset["size"] != version.file_size
            or not isinstance(asset.get("sha256"), str)
            or re.fullmatch("[0-9a-f]{64}", asset["sha256"]) is None
            or asset["sha256"] != version.media_identity
        ):
            raise PlaybackGatewayError("local_video_rejected", 422)
        return asset

    def _open_identity(self, version, evidence=None):
        asset = self._asset(version)
        pending = (
            TaskArtifact.objects.filter(
                root="video", target_path=asset["path"], state="promoting"
            ).exists()
            if evidence is None
            else asset["path"] in evidence[0]
        )
        if pending:
            raise PlaybackGatewayError("local_publication_pending", 409)
        marker = (
            TaskAssetTarget.objects.filter(
                root="video", relative_path=asset["path"]
            ).first()
            if evidence is None
            else evidence[1].get(asset["path"])
        )
        if (
            marker is None
            or str(marker.marker) != asset.get("marker")
            or marker.sha256 != asset["sha256"]
        ):
            raise PlaybackGatewayError("local_media_removed", 410)
        fd = None
        try:
            fd = open_beneath(self.root, asset["path"])
            value = os.fstat(fd)
            if not stat.S_ISREG(value.st_mode) or value.st_size != asset["size"]:
                raise PlaybackGatewayError("media_identity_changed", 410)
            descriptor = {
                "schema": "version-local-playback-v1",
                "version_id": str(version.pk),
                "sha256": version.media_identity,
                "fingerprint": fingerprint(value),
                "marker": asset["marker"],
            }
            return fd, descriptor
        except BaseException:
            if fd is not None:
                os.close(fd)
            raise

    def identity(self, avid):
        version = self._version(avid)
        if version is None:
            return self.legacy.identity(avid)
        try:
            fd, descriptor = self._open_identity(version)
            os.close(fd)
            return descriptor
        except OSError:
            raise PlaybackGatewayError("local_media_unavailable", 410) from None

    def check(self, avid, expected):
        version = self._version(avid, expected)
        if version is None:
            return self.legacy.check(avid, expected)
        try:
            fd, actual = self._open_identity(version)
            os.close(fd)
            if actual != expected:
                raise PlaybackGatewayError("media_identity_changed", 410)
        except OSError:
            raise PlaybackGatewayError("local_media_unavailable", 410) from None

    def open(self, avid, expected):
        if self._version(avid, expected) is None:
            return self.legacy.open(avid, expected)
        try:
            with self.locked(avid):
                version = self._version(avid, expected)
                if version is None:
                    raise PlaybackGatewayError("media_identity_changed", 410)
                fd, actual = self._open_identity(version)
                if actual != expected:
                    os.close(fd)
                    raise PlaybackGatewayError("media_identity_changed", 410)
                return LocalVideo(fd)
        except TimeoutError:
            raise PlaybackGatewayError("local_video_busy", 409) from None
        except OSError:
            raise PlaybackGatewayError("local_media_unavailable", 410) from None

    def identities(self, avids):
        if not avids:
            return {}
        entries = list(
            held_entries(self.user_id)
            .filter(pool__canonical_avid__in=avids)
            .prefetch_related(None)
        )
        versions = {}
        paths = set()
        legacy = set()
        eligible = set(
            held_entries(self.user_id)
            .filter(pool__canonical_avid__in=avids)
            .filter(version_filter("video_version", self.user_id, "video"))
            .values_list("pk", flat=True)
        )
        for entry in entries:
            if entry.video_version is None and entry.access_scope in {
                "public",
                f"legacy:operator:{self.user_id}",
            }:
                legacy.add(entry.pool.canonical_avid)
            elif entry.pk in eligible:
                try:
                    asset = self._asset(entry.video_version)
                    versions[entry.pool.canonical_avid] = entry.video_version
                    paths.add(asset["path"])
                except PlaybackGatewayError:
                    continue
        evidence = (
            set(
                TaskArtifact.objects.filter(
                    root="video", target_path__in=paths, state="promoting"
                ).values_list("target_path", flat=True)
            ),
            {
                row.relative_path: row
                for row in TaskAssetTarget.objects.filter(
                    root="video", relative_path__in=paths
                )
            },
        )
        result = self.legacy.identities(legacy)
        for avid, version in versions.items():
            try:
                fd, result[avid] = self._open_identity(version, evidence)
                os.close(fd)
            except (PlaybackGatewayError, OSError):
                continue
        return result
