"""Authorize a fixed version before opening any versioned image bytes."""

from typing import Protocol
from typing import BinaryIO, Callable
from uuid import uuid4

from loguru import logger
from nassav.resource_reads import ReadLeaseNotFound


class ImageLocator(Protocol):
    def open(
        self, version, asset_id, authorize: Callable[[], None]
    ) -> tuple[BinaryIO, str, int]: ...


class LeasedImage:
    def __init__(self, handle, reads, user_id, key, lease):
        self.handle, self.reads, self.user_id, self.key, self.lease = (
            handle,
            reads,
            user_id,
            key,
            lease,
        )

    def read(self, size=-1):
        if self.handle is None:
            raise ReadLeaseNotFound("Image stream closed")
        self.reads.check(self.user_id, self.key, self.lease["lease_id"])
        data = self.handle.read(size)
        self.reads.check(self.user_id, self.key, self.lease["lease_id"])
        return data

    def close(self):
        if self.handle is not None:
            self.handle.close()
            self.handle = None
            try:
                self.reads.release(self.user_id, self.key, self.lease["lease_id"])
            except Exception:
                # Logout/removal may deny cleanup; the bounded lease expires.
                logger.warning("Version image read lease release was denied")


class LibraryImages:
    def __init__(self, reads, locator: ImageLocator):
        self.reads, self.locator = reads, locator

    def open(self, user_id, key, version, asset_id=None):
        lease = None
        handle = None

        def authorize():
            nonlocal lease
            lease = self.reads.pin(user_id, key, version.pk, uuid4())

        try:
            handle, content_type, size = self.locator.open(version, asset_id, authorize)
            if lease is None:
                handle.close()
                raise RuntimeError("Image locator skipped authorization")
            self.reads.check(user_id, key, lease["lease_id"])
        except BaseException:
            if handle is not None:
                handle.close()
            if lease is not None:
                try:
                    self.reads.release(user_id, key, lease["lease_id"])
                except Exception:
                    logger.warning("Failed image read lease release was denied")
            raise
        return LeasedImage(handle, self.reads, user_id, key, lease), content_type, size

    @staticmethod
    def require_version(entry):
        if entry.state != "active" or entry.current_version is None:
            raise ReadLeaseNotFound("Version image not available")
        return entry.current_version
