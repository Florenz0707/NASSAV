"""Fixed-version read lease validation, independent of HTTP and storage."""

from typing import Protocol
from uuid import UUID


class ReadLeaseConflict(RuntimeError):
    pass


class ReadLeaseNotFound(LookupError):
    pass


class ReadLeaseRecords(Protocol):
    def pin(
        self,
        user_id: int,
        key: str,
        version_id: UUID,
        request_id: UUID,
        playback_session_id: UUID | None,
    ) -> dict: ...

    def renew(self, user_id: int, key: str, lease_id: UUID, revision: int) -> dict: ...

    def release(self, user_id: int, key: str, lease_id: UUID) -> dict: ...

    def check(self, user_id: int, key: str, lease_id: UUID) -> dict: ...


class VersionReads:
    def __init__(self, records: ReadLeaseRecords):
        self.records = records

    @staticmethod
    def actor(user_id, key):
        if (
            type(user_id) is not int
            or user_id < 1
            or not isinstance(key, str)
            or not key
            or len(key) > 64
        ):
            raise ValueError("Invalid read actor")

    @staticmethod
    def identity(value):
        try:
            return UUID(str(value))
        except (ValueError, TypeError):
            raise ValueError("Invalid read identity") from None

    def pin(self, user_id, key, version_id, request_id, *, playback_session_id=None):
        self.actor(user_id, key)
        return self.records.pin(
            user_id,
            key,
            self.identity(version_id),
            self.identity(request_id),
            self.identity(playback_session_id)
            if playback_session_id is not None
            else None,
        )

    def renew(self, user_id, key, lease_id, *, expected_revision):
        self.actor(user_id, key)
        if type(expected_revision) is not int or expected_revision < 1:
            raise ValueError("Invalid read revision")
        return self.records.renew(
            user_id, key, self.identity(lease_id), expected_revision
        )

    def check(self, user_id, key, lease_id):
        self.actor(user_id, key)
        return self.records.check(user_id, key, self.identity(lease_id))

    def release(self, user_id, key, lease_id):
        self.actor(user_id, key)
        return self.records.release(user_id, key, self.identity(lease_id))
